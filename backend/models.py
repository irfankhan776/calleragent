from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from sqlmodel import SQLModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CallJob(SQLModel, table=True):
    id: str = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    status: str = Field(default=JobStatus.PENDING.value)
    business_name: str
    phone_number: str
    business_type: str
    dry_run: bool = False
    limit: Optional[int] = Field(default=None)
    call_id: Optional[str] = Field(default=None)
    outcome: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)


class Call(SQLModel, table=True):
    id: str = Field(default=None, primary_key=True)
    business_name: str
    phone_number: str
    business_type: str
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: int
    outcome: str
    transcript: str
    recording_path: str
    sentiment: str
    notes: Optional[str] = Field(default=None)
