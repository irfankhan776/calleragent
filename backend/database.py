import os
from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./smartreception.db")

# Adjust Postgres URL if needed for newer SQLAlchemy (replace postgres:// with postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Connect argument check: sqlite needs check_same_thread=False
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)


def init_db():
    recordings_dir = os.environ.get("RECORDINGS_DIR", "./recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
