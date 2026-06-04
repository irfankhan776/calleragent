"""
server.py

FastAPI server that:
1. /start  — Initiates outbound call via Telnyx TeXML REST API
2. /answer — Serves TeXML that tells Telnyx where to WebSocket-connect
3. /ws     — Accepts Telnyx WebSocket, runs the Pipecat bot

This is the ONLY supported self-hosted outbound calling pattern for Telnyx + Pipecat.
"""

import base64
import json
import os
import urllib.parse
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv(override=True)

app: FastAPI = None


# ── Helpers ──────────────────────────────────────────────────────────────────

async def make_telnyx_call(
    session: aiohttp.ClientSession,
    to_number: str,
    from_number: str,
    texml_url: str,
) -> dict:
    """Initiate an outbound call via Telnyx TeXML API."""
    api_key = os.getenv("TELNYX_API_KEY")
    account_sid = os.getenv("TELNYX_ACCOUNT_SID")
    application_sid = os.getenv("TELNYX_APPLICATION_SID")

    if not api_key:
        raise ValueError("TELNYX_API_KEY is not set")
    if not account_sid:
        raise ValueError("TELNYX_ACCOUNT_SID is not set — required for TeXML calls")
    if not application_sid:
        raise ValueError("TELNYX_APPLICATION_SID is not set — required for TeXML calls")
    if not from_number:
        raise ValueError("TELNYX_FROM_NUMBER is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "ApplicationSid": application_sid,
        "To": to_number,
        "From": from_number,
        "Url": texml_url,
    }

    url = f"https://api.telnyx.com/v2/texml/Accounts/{account_sid}/Calls"
    async with session.post(url, headers=headers, json=payload) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise Exception(f"Telnyx TeXML API error ({resp.status}): {text}")
        return await resp.json()


def get_websocket_url(host: str) -> str:
    """Return the WebSocket URL that Telnyx should connect to."""
    env = os.getenv("ENV", "local").lower()
    if env == "production":
        # For production: route to Pipecat Cloud (requires separate deployment)
        return "wss://api.pipecat.daily.co/ws/telnyx"
    # For self-hosted: point back to this server's /ws endpoint
    protocol = "https" if not host.startswith(("localhost", "127.", "0.0.")) else "http"
    return f"{protocol}://{host}/ws"


# ── Lifespan (aiohttp session) ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    fastapi_app.state.session = aiohttp.ClientSession()
    yield
    await fastapi_app.state.session.close()


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="SmartReception Agent — Outbound Dialer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def initiate_outbound_call(request: Request) -> JSONResponse:
    """
    Trigger an outbound call to `phone_number`.
    Optionally pass `body` dict with business_name, business_type for personalization.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    phone_number = data.get("phone_number")
    if not phone_number:
        raise HTTPException(status_code=400, detail="Missing 'phone_number' in request body")

    body_data = data.get("body", {})
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    protocol = "https" if not host.startswith(("localhost", "127.", "0.0.")) else "http"
    texml_url = f"{protocol}://{host}/answer"

    if body_data:
        body_json = json.dumps(body_data)
        body_b64 = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
        encoded_body = urllib.parse.quote(body_b64, safe="")
        texml_url = f"{texml_url}?body={encoded_body}"

    try:
        result = await make_telnyx_call(
            session=request.app.state.session,
            to_number=phone_number,
            from_number=os.getenv("TELNYX_FROM_NUMBER"),
            texml_url=texml_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Telnyx call initiation failed: {e}")

    call_control_id = None
    if "data" in result:
        call_control_id = (
            result["data"].get("call_control_id")
            or result["data"].get("call_control_id")
            or result["data"].get("sid")
        )

    return JSONResponse({
        "call_control_id": call_control_id or "unknown",
        "status": "call_initiated",
        "phone_number": phone_number,
    })


@app.post("/answer")
async def get_answer_xml(request: Request) -> HTMLResponse:
    """
    Telnyx calls this endpoint after the outbound call is answered.
    Returns TeXML that tells Telnyx where to open the WebSocket for audio.
    """
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=500, detail="No host header")

    ws_url = get_websocket_url(host)
    query_parts = []

    if request.query_params and "body" in request.query_params:
        query_parts.append(f"body={request.query_params['body']}")

    if query_parts:
        ws_url = f"{ws_url}?{'&'.join(query_parts)}"

    env = os.getenv("ENV", "local").lower()
    if env == "production":
        agent_name = os.getenv("AGENT_NAME", "")
        org_name = os.getenv("ORGANIZATION_NAME", "")
        if agent_name and org_name:
            ws_url = f"{ws_url}&serviceHost={agent_name}.{org_name}"

    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" bidirectionalMode="rtp"></Stream>
  </Connect>
  <Pause length="40"/>
</Response>"""

    return HTMLResponse(content=texml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Telnyx connects here after answering. Run the Pipecat bot."""
    await websocket.accept()

    body_data = {}
    if body:
        try:
            url_decoded = urllib.parse.unquote(body)
            body_data = json.loads(base64.b64decode(url_decoded).decode("utf-8"))
        except Exception:
            pass  # Use empty dict on decode failure

    try:
        from bot import bot
        from pipecat.runner.types import WebSocketRunnerArguments

        runner_args = WebSocketRunnerArguments(
            websocket=websocket,
            body=body_data,
        )
        await bot(runner_args)
    except Exception as e:
        print(f"[WS] Bot error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("AGENT_PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
