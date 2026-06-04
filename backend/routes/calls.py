import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlmodel import Session, select, func, and_, or_

from database import get_session, engine
from models import Call, CallJob, JobStatus
from sentiment import detect_sentiment

router = APIRouter(prefix="/calls", tags=["calls"])


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

    # Also save to disk for local dev convenience (not used in production)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(root_dir, "businesses.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(content_str)

    csv_lines = [l for l in lines[1:] if l.strip()]
    row_count = len(csv_lines)

    # Store CSV content directly in the job record so the agent can fetch it
    # regardless of whether it shares a filesystem with the backend.
    job_id = str(uuid.uuid4())
    with Session(engine) as db_session:
        job = CallJob(
            id=job_id,
            business_name="BATCH_IMPORT",
            phone_number=f"job:{job_id}",  # markers the job source
            business_type=f"{row_count} businesses",
            dry_run=dry_run,
            limit=limit,
            csv_content=content_str,  # agent fetches this via /jobs/{id}/csv
        )
        db_session.add(job)
        db_session.commit()

    return {
        "status": "success",
        "message": f"CSV uploaded ({row_count} businesses). Dialer job queued.",
        "job_id": job_id,
        "row_count": row_count
    }
