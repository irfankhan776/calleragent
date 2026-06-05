"""
worker.py

SmartReception Agent Worker
Polls the backend for pending CSV batch jobs, then triggers outbound calls
by calling the agent's /start endpoint (which uses Telnyx TeXML API).

Architecture:
  worker.py ──POST /start──> server.py ──TeXML API──> Telnyx ──calls──> recipient
                               │
                               └── /ws (WebSocket) ──> bot.py (Pipecat pipeline)
                               │
                               └── POST /calls (result) ──> backend
"""

import os
import sys
import asyncio
import logging
import csv
import io
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("agent-worker")

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
BACKEND_URL  = os.environ.get("BACKEND_URL", "").rstrip("/")
AGENT_URL    = os.environ.get("AGENT_URL", "").rstrip("/")    # agent server base URL
POLL_INTERVAL = int(os.environ.get("AGENT_POLL_INTERVAL", "10"))
API_TIMEOUT   = 30.0

if AGENT_URL and not AGENT_URL.startswith(("http://", "https://")):
    AGENT_URL = f"https://{AGENT_URL}"

if not BACKEND_URL:
    log.error("BACKEND_URL is not set! Set it in Railway → agent variables.")
    sys.exit(1)

if not AGENT_URL:
    log.error(
        "AGENT_URL is not set! Set it in Railway → agent variables to your "
        "agent's public HTTPS URL (e.g. https://your-agent.up.railway.app). "
        "This is needed for Telnyx to reach /answer and /ws."
    )
    sys.exit(1)

log.info(f"Worker starting — backend: {BACKEND_URL}, agent: {AGENT_URL}")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def claim_job(client: httpx.AsyncClient) -> dict | None:
    try:
        resp = await client.post(f"{BACKEND_URL}/jobs/claim", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            payload = resp.json()
            if not isinstance(payload, dict):
                log.error(f"Claim response was not a JSON object: {payload!r}")
                return None
            job_id = payload.get("id")
            if not job_id:
                log.error(f"Claim response missing id: {payload}")
                return None
            return payload
        if resp.status_code == 204:
            return None
        log.warning(f"Unexpected claim response: {resp.status_code} {resp.text}")
        return None
    except Exception as e:
        log.error(f"Failed to claim job: {e}")
        return None


async def patch_job(client: httpx.AsyncClient, job_id: str, **fields):
    payload = {"status": fields.pop("status"), **fields}
    try:
        await client.patch(f"{BACKEND_URL}/jobs/{job_id}", json=payload, timeout=API_TIMEOUT)
    except Exception as e:
        log.error(f"Failed to update job {job_id}: {e}")


async def report_call_result(client: httpx.AsyncClient, job_id: str, step: int, result: dict):
    """Post a structured per-call result to the backend so the UI can track progress."""
    try:
        await client.post(
            f"{BACKEND_URL}/jobs/{job_id}/results",
            json={
                "step": step,
                "type": result.get("type", "call"),
                "level": result.get("level", "info"),
                "business_name": result.get("business_name", ""),
                "phone_number": result.get("phone_number", ""),
                "business_type": result.get("business_type", ""),
                "status": result.get("status", "unknown"),
                "outcome": result.get("outcome", ""),
                "error": result.get("error", ""),
                "title": result.get("title", ""),
                "detail": result.get("detail", ""),
                "note": result.get("note", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        log.warning(f"Failed to report call result to backend: {e}")


async def trigger_outbound_call(
    client: httpx.AsyncClient,
    business_name: str,
    phone_number: str,
    business_type: str,
) -> dict:
    """
    POST to the agent server's /start endpoint to initiate an outbound call.
    Returns {"call_control_id": ..., "status": ..., "phone_number": ...}
    """
    resp = await client.post(
        f"{AGENT_URL}/start",
        json={
            "phone_number": phone_number,
            "body": {
                "business_name": business_name,
                "business_type": business_type,
                "phone_number": phone_number,
            },
        },
        timeout=API_TIMEOUT,
    )
    if resp.status_code != 200:
        raise Exception(f"Agent /start failed: {resp.status_code} {resp.text}")
    return resp.json()


# ── Job Processing ─────────────────────────────────────────────────────────────

async def process_batch_job(client: httpx.AsyncClient, job: dict):
    job_id = job["id"]
    dry_run = job.get("dry_run", False)
    limit = job.get("limit")
    failures = 0
    initiated = 0

    log.info(f"[Job {job_id[:8]}] Starting batch — dry_run={dry_run}, limit={limit}")
    await report_call_result(client, job_id, 0, {
        "type": "event",
        "level": "info",
        "status": "worker_claimed",
        "title": "Worker claimed campaign",
        "detail": f"Worker picked up job {job_id[:8]} and started processing.",
    })

    # ── 1. Fetch CSV from backend ────────────────────────────────────────────
    try:
        resp = await client.get(f"{BACKEND_URL}/jobs/{job_id}/csv", timeout=API_TIMEOUT)
        if resp.status_code != 200:
            raise Exception(f"Backend returned {resp.status_code}")
        csv_content = resp.json().get("csv_content", "")
    except Exception as e:
        log.error(f"[Job {job_id[:8]}] Failed to fetch CSV: {e}")
        await report_call_result(client, job_id, 0, {
            "type": "event",
            "level": "error",
            "status": "failed",
            "title": "Failed to fetch CSV",
            "detail": str(e),
            "error": str(e),
        })
        await patch_job(client, job_id, status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message=f"CSV fetch failed: {e}")
        return

    # ── 2. Parse CSV ────────────────────────────────────────────────────────
    businesses = []
    reader = csv.DictReader(io.StringIO(csv_content))
    col_map = {}
    for original in (reader.fieldnames or []):
        n = original.strip().lower()
        if "name" in n and "name" not in col_map:     col_map["name"] = original
        elif "phone" in n and "phone" not in col_map: col_map["phone"] = original
        elif "type" in n and "type" not in col_map:   col_map["type"] = original

    for row in reader:
        businesses.append({
            "name":  row.get(col_map.get("name",  ""), "").strip(),
            "phone": row.get(col_map.get("phone", ""), "").strip(),
            "type":  row.get(col_map.get("type",  ""), "").strip(),
        })

    if limit:
        businesses = businesses[:limit]

    if not businesses:
        await report_call_result(client, job_id, 0, {
            "type": "event",
            "level": "error",
            "status": "failed",
            "title": "No valid rows to call",
            "detail": "CSV parsed successfully but no valid business rows were found.",
            "error": "CSV empty or no valid rows",
        })
        await patch_job(client, job_id, status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message="CSV empty or no valid rows")
        return

    await patch_job(client, job_id, status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        notes=f"Processing {len(businesses)} business(es)")
    await report_call_result(client, job_id, 0, {
        "type": "event",
        "level": "info",
        "status": "running",
        "title": "Campaign running",
        "detail": f"Starting {len(businesses)} call attempt(s).",
    })

    # ── 3. Trigger calls ────────────────────────────────────────────────────
    for i, biz in enumerate(businesses, start=1):
        log.info(f"[{i}/{len(businesses)}] Triggering call to {biz['name']} at {biz['phone']}...")
        call_result = {
            "type": "call",
            "level": "info",
            "business_name": biz["name"],
            "phone_number": biz["phone"],
            "business_type": biz["type"],
            "status": "unknown",
            "outcome": "",
            "error": "",
            "title": f"Call attempt #{i}",
            "detail": "",
            "note": "",
        }
        try:
            if dry_run:
                log.info(f"  [dry_run] Would call {biz['phone']} — skipping Telnyx")
                initiated += 1
                call_result["status"] = "simulated"
                call_result["outcome"] = "Dry run — no real call placed"
                call_result["detail"] = f"Simulation only for {biz['name']}"
                call_result["note"] = f"DRY RUN: {biz['name']} at {biz['phone']} ({biz['type']})"
            else:
                result = await trigger_outbound_call(
                    client,
                    business_name=biz["name"],
                    phone_number=biz["phone"],
                    business_type=biz["type"],
                )
                initiated += 1
                log.info(f"  -> call_initiated: {result.get('call_control_id', 'unknown')}")
                call_result["status"] = "initiated"
                call_result["outcome"] = "Call initiated"
                call_result["detail"] = f"Agent accepted outbound call request for {biz['phone']}"
                call_result["note"] = f"Call control ID: {result.get('call_control_id', 'N/A')}"
        except Exception as e:
            failures += 1
            log.error(f"  -> Failed to trigger call: {e}")
            call_result["level"] = "error"
            call_result["status"] = "error"
            call_result["error"] = str(e)
            call_result["detail"] = str(e)
            call_result["note"] = f"FAILED: {e}"

        await report_call_result(client, job_id, i, call_result)
        await asyncio.sleep(2)

    final_status = "completed"
    final_error = None
    final_notes = f"Batch done. {initiated} initiated/simulated, {failures} failed."

    if failures == len(businesses):
        final_status = "failed"
        final_error = "All call attempts failed before a call could be started."
    elif failures > 0:
        final_notes += " Some calls failed — review error log below."

    await report_call_result(client, job_id, 999999, {
        "type": "event",
        "level": "error" if final_status == "failed" else "info",
        "status": final_status,
        "title": "Campaign finished",
        "detail": final_error or final_notes,
        "error": final_error or "",
    })
    await patch_job(client, job_id, status=final_status,
        completed_at=datetime.now(timezone.utc).isoformat(),
        notes=final_notes,
        error_message=final_error)
    log.info(f"[Job {job_id[:8]}] Batch completed with status={final_status}.")


# ── Main Loop ─────────────────────────────────────────────────────────────────

async def worker_loop():
    log.info(f"Polling backend every {POLL_INTERVAL}s...")
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        while True:
            job = await claim_job(client)
            if job:
                job_id = job.get("id")
                if not job_id:
                    log.error(f"Skipping claimed job with missing id: {job}")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                log.info(f"Claimed job: {job_id}")
                await process_batch_job(client, job)
            else:
                await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        log.info("Worker shutting down.")
    except Exception as e:
        log.critical(f"Worker crashed: {e}")
        sys.exit(1)
