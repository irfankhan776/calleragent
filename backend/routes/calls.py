import os
import uuid
import json
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlmodel import Session, select, func, and_, or_

from database import get_session, engine
from models import Call, CallJob, JobStatus
from sentiment import detect_sentiment

router = APIRouter(prefix="/calls", tags=["calls"])


def _parse_allowed_origins(raw: str) -> list[str]:
    if not raw or raw == "*":
        return []
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


def _build_preflight_status(*, dry_run: bool) -> dict:
    backend_url = os.environ.get("BACKEND_URL", "").rstrip("/")
    agent_url = os.environ.get("AGENT_URL", "").rstrip("/")
    cors_origin = os.environ.get("CORS_ORIGIN", "")
    allowed_origins = _parse_allowed_origins(cors_origin)

    checks = []
    errors = []
    warnings = []

    def add_check(name: str, ok: bool, detail: str):
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            errors.append(f"{name}: {detail}")

    backend_url_ok = bool(backend_url) and not any(local in backend_url for local in ["localhost", "127.0.0.1", "0.0.0.0"])
    add_check(
        "BACKEND_URL",
        backend_url_ok,
        "must be set to the deployed backend URL and cannot point to localhost"
    )

    agent_url_ok = bool(agent_url) and not any(local in agent_url for local in ["localhost", "127.0.0.1", "0.0.0.0"])
    add_check(
        "AGENT_URL",
        agent_url_ok,
        "must be set to the deployed agent URL and cannot point to localhost"
    )

    if dry_run:
        add_check("TELNYX_LIVE_CONFIG", True, "dry run enabled — live-call credentials not required")
    else:
        required_live_vars = {
            "TELNYX_API_KEY": os.environ.get("TELNYX_API_KEY"),
            "TELNYX_ACCOUNT_SID": os.environ.get("TELNYX_ACCOUNT_SID"),
            "TELNYX_APPLICATION_SID": os.environ.get("TELNYX_APPLICATION_SID"),
            "TELNYX_FROM_NUMBER": os.environ.get("TELNYX_FROM_NUMBER"),
        }
        missing_live_vars = [name for name, value in required_live_vars.items() if not value]
        add_check(
            "TELNYX_LIVE_CONFIG",
            len(missing_live_vars) == 0,
            "missing: " + ", ".join(missing_live_vars) if missing_live_vars else "all required Telnyx variables are present"
        )

    frontend_origin_hint = os.environ.get("VITE_API_BASE_URL", "").rstrip("/")
    if allowed_origins and frontend_origin_hint and frontend_origin_hint not in allowed_origins:
        warnings.append(
            f"VITE_API_BASE_URL is '{frontend_origin_hint}' but CORS_ORIGIN does not include it. "
            f"Current allowed origins: {', '.join(allowed_origins)}"
        )

    return {
        "ok": len(errors) == 0,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "summary": "Preflight passed" if len(errors) == 0 else "Preflight failed",
    }


async def _append_job_event(job_id: str, event: dict):
    with Session(engine) as db_session:
        job = db_session.get(CallJob, job_id)
        if not job:
            return
        existing = []
        if job.call_results:
            try:
                existing = json.loads(job.call_results)
            except Exception:
                existing = []
        existing.append(event)
        job.call_results = json.dumps(existing)
        db_session.add(job)
        db_session.commit()


class CallCreate(BaseModel):
    business_name: str
    phone_number: str
    business_type: str
    duration_seconds: int
    outcome: str
    transcript: str
    recording_path: str
    notes: Optional[str] = None


@router.post("", response_model=Call)
def create_call(call_data: CallCreate, session: Session = Depends(get_session)):
    call_id = str(uuid.uuid4())
    called_at = datetime.now(timezone.utc)
    sentiment = detect_sentiment(call_data.transcript)

    db_call = Call(
        id=call_id,
        business_name=call_data.business_name,
        phone_number=call_data.phone_number,
        business_type=call_data.business_type,
        called_at=called_at,
        duration_seconds=call_data.duration_seconds,
        outcome=call_data.outcome,
        transcript=call_data.transcript,
        recording_path=call_data.recording_path,
        sentiment=sentiment,
        notes=call_data.notes
    )

    session.add(db_call)
    session.commit()
    session.refresh(db_call)
    return db_call


@router.get("")
def get_calls(
    outcome: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_str: Optional[str] = Query(None, alias="date"),
    sort: str = Query("called_at"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session)
):
    query = select(Call)
    conditions = []

    if outcome:
        conditions.append(Call.outcome == outcome)

    if search:
        search_filter = or_(
            Call.business_name.like(f"%{search}%"),
            Call.phone_number.like(f"%{search}%"),
            Call.business_type.like(f"%{search}%"),
            Call.transcript.like(f"%{search}%")
        )
        conditions.append(search_filter)

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            conditions.append(Call.called_at >= day_start)
            conditions.append(Call.called_at <= day_end)
        except ValueError:
            pass

    if conditions:
        query = query.where(and_(*conditions))

    total_query = select(func.count()).select_from(query.subquery())
    total = session.exec(total_query).one()

    sort_column = getattr(Call, sort, Call.called_at)
    if order.lower() == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    query = query.offset(offset).limit(limit)
    calls = session.exec(query).all()

    return {
        "calls": calls,
        "total": total,
        "page_info": {
            "limit": limit,
            "offset": offset,
            "total": total
        }
    }


@router.get("/{call_id}", response_model=Call)
def get_call(call_id: str, session: Session = Depends(get_session)):
    call = session.get(Call, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@router.delete("/{call_id}")
def delete_call(call_id: str, session: Session = Depends(get_session)):
    call = session.get(Call, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    recordings_dir = os.environ.get("RECORDINGS_DIR", "./recordings")
    if call.recording_path:
        file_path = call.recording_path
        if not os.path.isabs(file_path):
            file_path = os.path.join(recordings_dir, os.path.basename(file_path))
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error removing recording file: {e}")

    session.delete(call)
    session.commit()
    return {"status": "success", "message": f"Call {call_id} and its recording deleted"}


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    limit: Optional[int] = Query(None),
    dry_run: bool = Query(False)
):
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content_str = content.decode("latin1")
        except Exception:
            raise HTTPException(status_code=400, detail="Failed to decode CSV file as text")

    lines = [line.strip() for line in content_str.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    header = lines[0].lower()
    if "name" not in header or "phone" not in header or "type" not in header:
        raise HTTPException(status_code=400, detail="CSV must contain name, phone, and type columns")

    csv_lines = [l for l in lines[1:] if l.strip()]
    row_count = len(csv_lines)
    if row_count == 0:
        raise HTTPException(status_code=400, detail="CSV has headers but no business rows")

    preflight = _build_preflight_status(dry_run=dry_run)
    if not preflight["ok"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Campaign rejected before start because required calling configuration is invalid.",
                "preflight": preflight,
            },
        )

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(root_dir, "businesses.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(content_str)

    job_id = str(uuid.uuid4())
    initial_events = [
        {
            "type": "event",
            "level": "info",
            "status": "accepted",
            "title": "Campaign accepted",
            "detail": f"CSV accepted with {row_count} row(s).",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "type": "event",
            "level": "info",
            "status": "preflight_passed",
            "title": "Preflight passed",
            "detail": preflight["summary"],
            "checks": preflight["checks"],
            "warnings": preflight["warnings"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    ]

    with Session(engine) as db_session:
        job = CallJob(
            id=job_id,
            business_name="BATCH_IMPORT",
            phone_number=f"job:{job_id}",
            business_type=f"{row_count} businesses",
            dry_run=dry_run,
            limit=limit,
            csv_content=content_str,
            call_results=json.dumps(initial_events),
            notes=f"Campaign queued for {row_count} row(s)",
        )
        db_session.add(job)
        db_session.commit()

    return {
        "status": "success",
        "message": f"CSV uploaded ({row_count} businesses). Dialer job queued.",
        "job_id": job_id,
        "row_count": row_count,
        "preflight": preflight,
    }
