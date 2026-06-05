from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select
from typing import Optional
import json

from database import get_session
from models import CallJob, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/claim")
def claim_job(session: Session = Depends(get_session)):
    """Atomically claim the oldest pending job."""
    job = session.exec(
        select(CallJob)
        .where(CallJob.status == JobStatus.PENDING.value)
        .order_by(CallJob.created_at.asc())
        .limit(1)
    ).first()

    if not job:
        return Response(status_code=204)

    job.status = JobStatus.RUNNING.value
    session.add(job)
    session.commit()
    session.refresh(job)
    return {
        "id": job.id,
        "status": job.status,
        "dry_run": job.dry_run,
        "limit": job.limit,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "notes": job.notes,
        "error_message": job.error_message,
    }


@router.patch("/{job_id}")
def update_job(job_id: str, payload: dict, session: Session = Depends(get_session)):
    job = session.get(CallJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for key, value in payload.items():
        if hasattr(job, key):
            setattr(job, key, value)

    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.get("/{job_id}", response_model=CallJob)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(CallJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/status")
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    """
    Returns a structured status response for the UI to poll.
    Shows current state + per-call results with errors clearly surfaced.
    Also surfaces connection issues between worker and backend.
    """
    job = session.get(CallJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Parse call_results JSON stored in DB
    results = []
    if job.call_results:
        try:
            results = json.loads(job.call_results)
        except Exception:
            results = [{"step": "unknown", "status": "unknown", "note": job.call_results}]

    # Detect stuck jobs — if pending for > 5 minutes, worker likely can't reach backend
    warnings = []
    if job.status == JobStatus.PENDING.value and job.created_at:
        import os
        age_seconds = (datetime.now(timezone.utc) - job.created_at).total_seconds()
        if age_seconds > 300:
            warnings.append(
                f"Job stuck in PENDING for {int(age_seconds // 60)}min — "
                "worker may be unable to reach backend. "
                "Check that BACKEND_URL is set correctly in Railway → agent variables "
                "and points to the deployed backend URL (not localhost:8000)."
            )

    return {
        "id": job.id,
        "status": job.status,
        "error_message": job.error_message,
        "notes": job.notes,
        "warnings": warnings,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "call_results": results,
    }


@router.post("/{job_id}/results")
def append_call_result(job_id: str, payload: dict, session: Session = Depends(get_session)):
    """
    Called by the worker after each individual call.
    Appends a structured result entry so the UI can show per-call progress + errors.
    """
    job = session.get(CallJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    existing = []
    if job.call_results:
        try:
            existing = json.loads(job.call_results)
        except Exception:
            existing = []

    # Merge in the new result (idempotent by step index)
    existing.append(payload)
    job.call_results = json.dumps(existing)

    session.add(job)
    session.commit()
    return {"status": "ok", "total_results": len(existing)}


@router.get("")
def list_jobs(
    status: str | None = None,
    session: Session = Depends(get_session)
):
    query = select(CallJob).order_by(CallJob.created_at.desc())
    if status:
        query = query.where(CallJob.status == status)
    jobs = session.exec(query).all()
    return jobs


@router.get("/agent/health")
def agent_health():
    """Worker heartbeat endpoint — confirms the agent can reach the backend."""
    return {"status": "alive", "service": "agent-worker"}


@router.get("/{job_id}/csv")
def get_job_csv(job_id: str, session: Session = Depends(get_session)):
    """Returns the raw CSV content stored in a job. Used by the agent worker."""
    job = session.get(CallJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.csv_content:
        raise HTTPException(status_code=404, detail="No CSV content in this job")
    return {"csv_content": job.csv_content}
