import os
import asyncio
import logging
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("webhooks")


def get_backend_url() -> str:
    """Resolve the backend URL with Railway internal DNS fallback."""
    url = os.environ.get("BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")

    railway_internal = os.environ.get("RAILWAY_PRIVATE_URL", "").strip()
    if railway_internal:
        return railway_internal.rstrip("/")

    return "http://localhost:8000"


def post_call_data(
    business_name: str,
    phone_number: str,
    business_type: str,
    duration_seconds: int,
    outcome: str,
    transcript: str,
    recording_path: str,
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> dict | None:
    """
    POST call results to the backend with exponential backoff retry.
    Works on Railway (uses BACKEND_URL), Docker Compose (uses internal DNS),
    and local dev (falls back to localhost).
    """
    backend_url = get_backend_url()
    url = f"{backend_url}/calls"

    payload = {
        "business_name": business_name,
        "phone_number": phone_number,
        "business_type": business_type,
        "duration_seconds": duration_seconds,
        "outcome": outcome,
        "transcript": transcript,
        "recording_path": recording_path,
    }

    log.info(f"POSTing call data to {url} - {business_name} | {outcome}")

    async def _post() -> dict | None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code in (200, 201):
                data = response.json()
                log.info(f"Call saved! ID: {data.get('id')} | Sentiment: {data.get('sentiment')}")
                return data
            else:
                log.error(f"Backend error {response.status_code}: {response.text}")
                return None

    async def _post_with_retry() -> dict | None:
        for attempt in range(max_retries):
            result = await _post()
            if result:
                return result
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning(f"Retry {attempt + 1}/{max_retries} in {delay}s...")
                await asyncio.sleep(delay)
        return None

    try:
        return asyncio.run(_post_with_retry())
    except Exception as e:
        log.error(f"Exception posting call data: {e}")
        return None
