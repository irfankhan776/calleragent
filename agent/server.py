"""
server.py

SmartReception Agent-Web — FastAPI Entry Point

Replaces the old Pipecat-based server.py.
This is the ONLY deployed web process in the agent stack.
Handles:
  POST /start   — initiate outbound TeXML call
  GET  /answer  — TeXML webhook (Telnyx fetches this after answering)
  WS   /ws/<call_id>  — Telnyx media streaming WebSocket
  GET  /health  — health check for Railway

One of these runs per Railway agent-web service instance.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import urllib.parse
import uuid
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv(override=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agent-web")


# ── Lifespan ─────────────────────────────────────────────────────────────────
_active_sessions: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Agent-web starting...")
    yield
    log.info("Agent-web shutting down...")


# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SmartReception Agent-Web",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_public_base_url(request: Request) -> str:
    """
    Resolve the public HTTPS URL for this service.
    Uses AGENT_URL env var (set in Railway), falls back to Host header.
    """
    agent_url = os.environ.get("AGENT_URL", "").strip()
    if agent_url:
        return agent_url.rstrip("/")

    # Local dev fallback
    host = request.headers.get("host", "localhost:8000")
    protocol = "https" if not host.startswith(("localhost", "127.", "0.0.")) else "http"
    return f"{protocol}://{host}"


def get_telnyx_headers() -> dict:
    api_key = os.environ.get("TELNYX_API_KEY", "")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def initiate_texml_call(phone_number: str, from_number: str, answer_url: str) -> str:
    """
    Create an outbound TeXML call via Telnyx.
    Returns the call_control_id.
    """
    api_key = os.environ.get("TELNYX_API_KEY", "")
    account_sid = os.environ.get("TELNYX_ACCOUNT_SID", "")
    application_sid = os.environ.get("TELNYX_APPLICATION_SID", "")

    if not all([api_key, account_sid, application_sid]):
        raise ValueError(
            "TELNYX_API_KEY, TELNYX_ACCOUNT_SID, and TELNYX_APPLICATION_SID must all be set"
        )

    import httpx
    url = f"https://api.telnyx.com/v2/texml/Accounts/{account_sid}/Calls"
    payload = {
        "ApplicationSid": application_sid,
        "To": phone_number,
        "From": from_number,
        "Url": answer_url,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=get_telnyx_headers(), json=payload)
        if resp.status_code not in (200, 201):
            raise Exception(f"TeXML call failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        call_control_id = (
            data.get("data", {}).get("call_control_id")
            or data.get("data", {}).get("id")
            or data.get("call_control_id")
            or data.get("id")
        )
        if not call_control_id:
            raise Exception(f"No call_control_id in response: {data}")
        return call_control_id


# In-memory call data store (cleared on restart — fine for stateless web workers)
_call_data_map: dict[str, dict] = {}


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent-web"}


@app.post("/start")
async def start_call(request: Request) -> JSONResponse:
    """
    Called by worker.py to initiate an outbound call.

    Body:
      {
        "phone_number": "+1...",
        "body": {
          "business_name": "...",
          "business_type": "...",
          "call_control_id": "..."   // optional, for Call Control mode
        }
      }

    Returns:
      {"call_control_id": "...", "status": "call_initiated"}
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    phone_number = data.get("phone_number")
    if not phone_number:
        raise HTTPException(status_code=400, detail="Missing 'phone_number'")

    body_data = data.get("body", {})
    base_url = get_public_base_url(request)

    # Build the TeXML answer URL — Telnyx will fetch this after answering.
    # The /answer endpoint returns TeXML with a <Stream> verb pointing to our WS.
    call_id = str(uuid.uuid4())
    answer_url = f"{base_url}/answer?call_id={call_id}"
    ws_url = f"{base_url}/ws/{call_id}"

    # Store call metadata before initiating — the /answer handler needs it.
    _call_data_map[call_id] = {
        **(body_data or {}),
        "phone_number": phone_number,
    }

    try:
        from_number = os.environ.get("TELNYX_FROM_NUMBER", "")
        call_control_id = await initiate_texml_call(
            phone_number=phone_number,
            from_number=from_number,
            answer_url=answer_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {e}")

    # Store call metadata for the /answer and /ws handlers
    _call_data_map[call_id]["call_control_id"] = call_control_id

    log.info(f"[{call_id[:8]}] Outbound call initiated -> {phone_number} (ccid={call_control_id})")

    return JSONResponse({
        "call_control_id": call_control_id,
        "status": "call_initiated",
        "phone_number": phone_number,
        "call_id": call_id,
    })



@app.get("/answer")
async def answer_webhook(
    request: Request,
    call_id: str = Query(None),
) -> HTMLResponse:
    """
    Telnyx fetches this after the outbound call is answered.
    Returns TeXML instructing Telnyx to stream audio to our WebSocket.

    The <Stream> verb opens a WebSocket to our /ws/{call_id} endpoint.
    """
    if not call_id:
        raise HTTPException(status_code=400, detail="Missing call_id")

    call_data = _call_data_map.get(call_id, {})
    base_url = get_public_base_url(request)

    # Encode call metadata for the WebSocket handler
    body_encoded = ""
    safe_data = {k: v for k, v in call_data.items() if k != "call_control_id"}
    if safe_data:
        body_json = json.dumps(safe_data)
        body_b64 = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
        body_encoded = urllib.parse.quote(body_b64, safe="")

    ws_url = f"{base_url}/ws/{call_id}"
    if body_encoded:
        ws_url = f"{ws_url}?body={body_encoded}"

    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}"
            track="both_tracks"
            bidirectionalMode="rtp"
            bidirectionalCodec="PCMU"
            bidirectionalSamplingRate="8000">
    </Stream>
  </Connect>
  <Pause length="3600"/>
</Response>"""

    return HTMLResponse(content=texml, media_type="application/xml")


@app.websocket("/ws/{call_id}")
async def stream_websocket(websocket: WebSocket, call_id: str, body: str = Query(None)):
    """
    Telnyx opens this WebSocket after the call is answered.
    Audio flows bidirectionally: Telnyx sends RTP frames, we send audio back.

    We hand off to runtime.handle_stream_websocket for the actual AI pipeline.
    """
    # Decode body data
    body_data = {}
    if body:
        try:
            url_decoded = urllib.parse.unquote(body)
            body_data = json.loads(base64.b64decode(url_decoded).decode("utf-8"))
        except Exception:
            pass

    # Merge in stored call data
    stored = _call_data_map.pop(call_id, {})
    body_data = {**stored, **body_data}
    body_data.setdefault("call_id", call_id)

    log.info(f"[{call_id[:8]}] WebSocket connected")

    try:
        from runtime import handle_stream_websocket
        await handle_stream_websocket(websocket, call_id, body_data)
    except WebSocketDisconnect:
        log.info(f"[{call_id[:8]}] WebSocket disconnected")
    except Exception as e:
        log.error(f"[{call_id[:8]}] WebSocket handler error: {e}", exc_info=True)
    finally:
        _call_data_map.pop(call_id, None)


# ── Standalone Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        workers=1,
    )
