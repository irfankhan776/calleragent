"""
SmartReception Agent Worker
Polls the backend job queue, processes calls, and posts results back.
Runs as a standalone Railway service.
"""

import os
import sys
import asyncio
import logging
import csv
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("agent-worker")

# Load environment
load_dotenv()

# ── Configuration ──────────────────────────────────────────
BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
POLL_INTERVAL = int(os.environ.get("AGENT_POLL_INTERVAL", "10"))
API_TIMEOUT = 30.0

if not BACKEND_URL:
    log.error("BACKEND_URL is not set! Set it to your Railway backend URL.")
    sys.exit(1)

# ── Import agent call logic ────────────────────────────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import make_call


# ── Job Processing ────────────────────────────────────────

async def claim_next_job(client: httpx.AsyncClient) -> dict | None:
    """Atomically claim the oldest pending job."""
    try:
        resp = await client.post(f"{BACKEND_URL}/jobs/claim", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 204:
            return None
        else:
            log.warning(f"Unexpected claim response: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        log.error(f"Failed to claim job: {e}")
        return None


async def update_job_status(client: httpx.AsyncClient, job_id: str, status: str, **fields):
    """Update job status in the backend."""
    payload = {"status": status, **fields}
    try:
        await client.patch(
            f"{BACKEND_URL}/jobs/{job_id}",
            json=payload,
            timeout=API_TIMEOUT
        )
    except Exception as e:
        log.error(f"Failed to update job {job_id}: {e}")


async def run_batch(csv_path: str, dry_run: bool, limit: int | None) -> str:
    """Read CSV and execute calls via make_call."""
    businesses = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            col_map = {}
            for original in (reader.fieldnames or []):
                normalized = original.strip().lower()
                if "name" in normalized and "name" not in col_map:
                    col_map["name"] = original
                elif "phone" in normalized and "phone" not in col_map:
                    col_map["phone"] = original
                elif "type" in normalized and "type" not in col_map:
                    col_map["type"] = original

            for row in reader:
                businesses.append({
                    "name": row.get(col_map.get("name", ""), "").strip(),
                    "phone": row.get(col_map.get("phone", ""), "").strip(),
                    "type": row.get(col_map.get("type", ""), "").strip(),
                })
    except Exception as e:
        log.error(f"Failed to read CSV {csv_path}: {e}")
        raise

    if limit:
        businesses = businesses[:limit]

    last_outcome = "N/A"
    for i, biz in enumerate(businesses, start=1):
        log.info(f"[{i}/{len(businesses)}] Calling {biz['name']} at {biz['phone']}...")
        try:
            outcome = await make_call(biz["name"], biz["phone"], biz["type"], dry_run=dry_run)
            last_outcome = outcome
            log.info(f"  -> {outcome}")
        except Exception as e:
            log.error(f"  -> Call failed: {e}")
        await asyncio.sleep(2)

    return last_outcome


async def process_batch_job(client: httpx.AsyncClient, job: dict):
    """Process a batch CSV import job."""
    job_id = job["id"]
    csv_path = job["phone_number"]
    dry_run = job.get("dry_run", False)
    limit = job.get("limit")

    log.info(f"[Job {job_id[:8]}] Starting batch - dry_run={dry_run}, limit={limit}")
    await update_job_status(
        client, job_id, "running",
        started_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        last_outcome = await run_batch(csv_path, dry_run=dry_run, limit=limit)
        await update_job_status(
            client, job_id, "completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            notes=f"Batch complete. Last outcome: {last_outcome}"
        )
        log.info(f"[Job {job_id[:8]}] Batch completed successfully.")
    except Exception as e:
        log.error(f"[Job {job_id[:8]}] Batch failed: {e}")
        await update_job_status(
            client, job_id, "failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message=str(e)
        )


async def worker_loop():
    """Main polling loop — the heartbeat of the worker."""
    log.info(f"Agent worker starting. Backend: {BACKEND_URL}")
    log.info(f"Polling every {POLL_INTERVAL}s for jobs.")

    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        poll_count = 0
        while True:
            job = await claim_next_job(client)
            if job:
                log.info(f"Claimed job: {job['id']}")
                await process_batch_job(client, job)
                poll_count = 0
            else:
                poll_count += 1
                if poll_count % 6 == 0:
                    log.debug("No jobs pending. Sleeping...")

            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        log.info("Worker shutting down.")
    except Exception as e:
        log.critical(f"Worker crashed: {e}")
        sys.exit(1)
