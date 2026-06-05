# SmartReception — AI Cold Calling System

An AI-powered cold calling system with a real-time voice agent, live dashboard, and batch dialing. The AI agent ("Mia") calls businesses, has natural conversations, and reports outcomes — all visible in a live dashboard.

![Dashboard Preview](https://img.shields.io/badge/status-production--ready-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/fastapi-0.111-green)
![React](https://img.shields.io/badge/react-18-cyan)

---

## Architecture

```
Railway Cloud
│
├── backend/  FastAPI + PostgreSQL  :8000
│   └── /calls /stats /jobs  (system of record)
│
├── dashboard/  React + Tailwind    :3000
│   └── Uploads CSV, monitors calls, shows analytics
│
├── agent-worker/  (background poller)
│   └── polls /jobs/claim  →  POST /start  →  agent-web
│
└── agent-web/  FastAPI + realtime voice pipeline
    └── POST /start  →  Telnyx TeXML  →  outbound call
        GET  /answer →  Telnyx fetches TeXML
        WS   /ws/{id} →  Telnyx streams audio ↔ AI pipeline
            Deepgram STT → Gemini Realtime → ElevenLabs TTS
            → back to Telnyx → callee's phone
```

### Voice Pipeline (per call)

```
Telnyx RTP (8kHz ulaw)  →  WebSocket  →  Deepgram STT (nova-2)
    →  Gemini Realtime (gemini-2.0-flash-exp)  →  ElevenLabs TTS
    →  back through WebSocket  →  Telnyx  →  callee
```

All call results (transcript, outcome, duration) POSTed to `/calls` on the backend.

---

## Features

- **AI Voice Agent (Mia)** — Realtime phone calls using direct Telnyx WebSocket streaming, Deepgram STT, ElevenLabs TTS, and Google Gemini Realtime API
- **Live Dashboard** — Realtime call monitoring, outcome tracking, sentiment analysis, and analytics
- **Batch Dialer** — Upload a CSV of businesses, Mia calls them one by one automatically
- **Job Queue** — Reliable background processing via database-backed job queue
- **Recording Storage** — All calls are saved as WAV files and playable in the dashboard

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Voice AI | Deepgram STT (nova-2), ElevenLabs TTS, Google Gemini Realtime |
| Telephony | Telnyx WebSocket media streaming (TeXML outbound, RTP bidirectional) |
| Backend | FastAPI, SQLModel, PostgreSQL, Uvicorn |
| Frontend | React 18, Tailwind CSS, React Query, Vite |
| Deployment | Railway, Docker, Docker Compose |

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (optional, for full stack)

### 1. Clone & Install Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Dashboard

```bash
cd dashboard
npm install
```

### 3. Configure Environment

```bash
cp ../.env.example ../.env
# Edit ../.env and fill in your API keys
```

### 4. Run with Docker Compose (Recommended)

```bash
# From the project root:
docker-compose up --build
```

This starts all services:
- **Backend**: http://localhost:8000
- **Dashboard**: http://localhost:3000
- **PostgreSQL**: on port 5432
- **Agent Worker**: polling for jobs

### 5. Run Manually (Backend + Dashboard separately)

```bash
# Terminal 1 — Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 — Dashboard
cd dashboard
npm run dev

# Terminal 3 — Agent Worker (in a new terminal)
cd agent
python worker.py
```

---

## API Keys Setup

Copy `.env.example` to `.env` and fill in:

| Variable | Service | Where to get it |
|---|---|---|
| `GOOGLE_API_KEY` | LLM (Gemini) | [Google AI Studio](https://aistudio.google.com) |
| `DEEPGRAM_API_KEY` | Speech-to-Text | [Deepgram Console](https://console.deepgram.com) |
| `ELEVENLABS_API_KEY` | Text-to-Speech | [ElevenLabs Dashboard](https://elevenlabs.io) |
| `ELEVENLABS_VOICE_ID` | Voice ID | ElevenLabs dashboard (e.g. `21m00Tcm4TlvDq8ikWAM` for Rachel) |
| `TELNYX_API_KEY` | Phone calls | [Telnyx Portal](https://portal.telnyx.com) |
| `TELNYX_CONNECTION_ID` | WebRTC | Telnyx portal → WebRTC → Connections |
| `TELNYX_FROM_NUMBER` | Caller ID | Your Telnyx phone number (e.g. `+12025551234`) |

> **Note:** Without API keys, the system runs in **simulation mode** — Mia generates realistic mock conversations so you can test the full pipeline without spending money on real calls.

---

## CSV Format

Upload a CSV with these columns (header row required):

```csv
name,phone,type
Acme Plumbing,+12025551234,plumber
Joe's Barber Shop,+12025559876,barbershop
Sunset Restaurant,+12025551122,restaurant
```

- `name` — Business name
- `phone` — E.164 phone number (e.g. `+12025551234`)
- `type` — Business category (used in Mia's opening script)

---

## Railway Deployment

Railway deploys **4 services** from this repo. Each has exactly one responsibility.

### Step 1 — Connect GitHub

1. Go to [railway.app](https://railway.app) and create a new project
2. Connect your GitHub repo containing the `smartreception/` directory
3. Railway will auto-detect all four services from `railway.toml`

### Step 2 — Provision PostgreSQL

1. Add a PostgreSQL plugin to your Railway project
2. Railway auto-injects `DATABASE_URL` — no configuration needed

### Step 3 — Deploy Backend

1. Deploy the **backend** service
2. Note the Railway public URL (e.g. `https://smartreception-backend.up.railway.app`)
3. Set environment variables:

```
CORS_ORIGIN=*
RECORDINGS_DIR=/app/recordings
DATABASE_URL=<auto-injected>
```

### Step 4 — Deploy Dashboard

1. Set `VITE_API_BASE_URL` to your backend URL
2. Railway builds the dashboard and embeds this URL at build time
3. Deploy the **dashboard** service

### Step 5 — Deploy Agent Worker

Set the following in the **agent-worker** service variables:

```
BACKEND_URL=https://your-backend-url.up.railway.app
AGENT_URL=https://your-agent-web-url.up.railway.app
AGENT_POLL_INTERVAL=10
```

Start command: `python worker.py`

Do **not** assign a public domain to this service. It is a background poller, not an HTTP server.

### Step 6 — Deploy Agent Web (with public domain)

Set the following in the **agent-web** service variables:

```
AGENT_URL=https://your-agent-web-url.up.railway.app
GOOGLE_API_KEY=<your Gemini key>
DEEPGRAM_API_KEY=<your Deepgram key>
ELEVENLABS_API_KEY=<your ElevenLabs key>
ELEVENLABS_VOICE_ID=<your voice id>
TELNYX_API_KEY=<your Telnyx key>
TELNYX_ACCOUNT_SID=<your Telnyx account SID>
TELNYX_APPLICATION_SID=<your TeXML application SID>
TELNYX_FROM_NUMBER=+1XXXXXXXXXX
BACKEND_URL=https://your-backend-url.up.railway.app
```

Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`

**Important:** Assign a public HTTPS domain to this service in Railway. Telnyx needs to connect to it.

### Step 7 — Persistent Storage

In Railway, add a **persistent volume** to the backend service:
- Mount path: `/app/recordings`
- Size: 1 GB (recommended)

### Service Summary

| Service | Start Command | Public Domain | Purpose |
|---------|---------------|---------------|---------|
| backend | `uvicorn main:app ...` | Yes | REST API, DB, recordings |
| dashboard | `npx serve dist ...` | Yes | React UI |
| agent-worker | `python worker.py` | No | Job queue poller |
| agent-web | `uvicorn server:app ...` | **Yes** | Telephony + AI voice |

---

## API Reference

### Backend Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/stats` | Dashboard statistics |
| `GET` | `/calls` | List calls (with filtering) |
| `POST` | `/calls` | Create a call record |
| `GET` | `/calls/{id}` | Get single call |
| `DELETE` | `/calls/{id}` | Delete a call |
| `GET` | `/calls/{id}/audio` | Stream call recording |
| `POST` | `/calls/upload` | Upload CSV and start batch dialer |
| `POST` | `/jobs/claim` | Worker: claim next pending job |
| `GET` | `/jobs/{id}` | Get job status |
| `GET` | `/jobs` | List all jobs |
| `PATCH` | `/jobs/{id}` | Update job status |

---

## Project Structure

```
smartreception/
├── railway.toml           # Railway deployment (4 services)
├── docker-compose.yml     # Local full-stack deployment
├── .env.example           # Environment variables template
├── .gitignore
│
├── backend/               # FastAPI REST API + PostgreSQL
│   ├── main.py           # App entry, CORS, routing
│   ├── database.py       # SQLModel + PostgreSQL/SQLite
│   ├── models.py         # Call & CallJob SQLModel tables
│   ├── sentiment.py       # Keyword-based sentiment detection
│   ├── requirements.txt
│   ├── Dockerfile
│   └── routes/
│       ├── calls.py      # CRUD + CSV upload
│       ├── stats.py      # Analytics endpoints
│       ├── audio.py      # Recording streaming
│       └── jobs.py       # Job queue management
│
├── dashboard/             # React frontend
│   ├── src/
│   │   ├── App.jsx       # Main app + tab navigation
│   │   ├── api/client.js # Axios API client
│   │   ├── hooks/        # React Query hooks
│   │   └── components/   # UI components
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
│
└── agent/                 # Voice AI calling agent
    ├── worker.py         # Background job queue poller
    ├── server.py         # FastAPI web server (replaces Pipecat)
    ├── runtime.py         # Realtime voice pipeline: Deepgram + Gemini + ElevenLabs
    ├── main.py           # Local CLI script only (NOT deployed)
    ├── webhooks.py       # Backend API integration helpers
    ├── pitch.py          # AI sales script (Mia)
    ├── call_runner.py    # Local batch CLI runner
    ├── requirements.txt  # Direct deps: deepgram, elevenlabs, google-genai
    └── Dockerfile         # Used by both agent-worker and agent-web services
```

---

## Testing the Deployment

### Smoke Test

```bash
# Backend health
curl https://your-backend.up.railway.app/health

# Should return:
# {"status":"ok","service":"smartreception-backend"}

# Stats endpoint
curl https://your-backend.up.railway.app/stats

# Upload CSV (dry run)
curl -X POST \
  -F "file=@test.csv" \
  -F "dry_run=true" \
  -F "limit=3" \
  https://your-backend.up.railway.app/calls/upload
```

### Dry Run (No Real Calls)

Always test with `dry_run=true` first. Mia will simulate conversations without making real phone calls or spending API credits.

### Real Calls

1. Make sure all API keys are set in Railway
2. Set `dry_run=false` in the upload form
3. Start with a limit of 5 calls
4. Watch the dashboard as calls appear in real-time

---

## Troubleshooting

### Dashboard shows CORS errors
Set `CORS_ORIGIN=*` in Railway backend variables, or set it to the exact dashboard URL.

### Agent worker isn't picking up jobs
- Check `BACKEND_URL` is set correctly in the agent service
- Check Railway logs for the agent service
- Verify the backend is up: `curl https://your-backend-url/health`

### Recordings not saving
Attach a persistent volume to the backend service at `/app/recordings`.

### Calls are robotic/slow
- Use `gemini-2.0-flash-exp` for realtime calls
- Ensure `interim_results=False` in Deepgram STT
- Try a higher-quality ElevenLabs voice
- Check network latency between Railway and Telnyx

### Database errors on startup
Wait for PostgreSQL to fully initialize. The backend retries connecting automatically. If using SQLite locally, ignore PostgreSQL errors.

---

## License

MIT — free to use, modify, and commercialize.
