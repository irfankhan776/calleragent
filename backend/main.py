import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from database import init_db, get_session
from routes import calls, stats, audio, jobs

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(
    title="SmartReception API",
    description="Backend API for managing AI call outcomes, recordings, and analytics",
    version="1.0.0"
)

# ── CORS Configuration ───────────────────────────────────
cors_raw = os.environ.get("CORS_ORIGIN", "http://localhost:5173")

if cors_raw == "*":
    origins = ["*"]
else:
    origins = [o.strip() for o in cors_raw.split(",")]
    for local in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        if local not in origins:
            origins.append(local)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True if origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup ───────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()

# ── Static Recordings Mount ────────────────────────────────
recordings_dir = os.environ.get("RECORDINGS_DIR", "./recordings")
os.makedirs(recordings_dir, exist_ok=True)
app.mount("/recordings", StaticFiles(directory=recordings_dir), name="recordings")

# ── Routers ────────────────────────────────────────────────
app.include_router(calls.router)
app.include_router(stats.router)
app.include_router(audio.router)
app.include_router(jobs.router)

# ── Health Check ──────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "smartreception-backend"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
