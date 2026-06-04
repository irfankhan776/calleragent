#!/bin/bash
# start.sh — Runs the FastAPI server + polling worker together on Railway.
# Railway service start command: bash start.sh

set -e

echo "[start] SmartReception Agent booting..."
echo "[start] BACKEND_URL=$BACKEND_URL"
echo "[start] AGENT_URL=$AGENT_URL"
echo "[start] AGENT_PORT=${AGENT_PORT:-7860}"

# Give the server a moment to bind before the worker starts polling
sleep 5

# Worker: polls backend for jobs, triggers /start on this same server
python -m agent.worker &
WORKER_PID=$!
echo "[start] Worker started (PID $WORKER_PID)"

# Server: serves /start (TeXML call initiation), /answer (TeXML webhook), /ws (bot)
exec uvicorn agent.server:app \
    --host 0.0.0.0 \
    --port "${AGENT_PORT:-7860}" \
    --limit-concurrency 10
