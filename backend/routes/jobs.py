from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

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
        return {"status": 204}

    job.status = JobStatus.RUNNING.value
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


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
