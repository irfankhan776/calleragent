"""
bot.py

Pipecat 1.x bot for outbound Telnyx calls.
Receives WebSocket connections from Telnyx (after outbound call is answered),
runs the full voice AI pipeline, then posts results back to the backend.
"""

import asyncio
import os
import time
import wave
import uuid
import logging

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.frames.frames import Frame, TextFrame, UserTranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.services.google import GoogleLLMService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams

from pitch import SYSTEM_PROMPT

# ── Logging ──────────────────────────────────────────────────────────────────
logger.remove()
logger.add(
    lambda msg: print(msg.text),
    level=logging.INFO,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


# ── Transcript Accumulator ────────────────────────────────────────────────────

class TranscriptAccumulator(FrameProcessor):
    """Collects transcript text from user/assistant frames for outcome extraction."""

    def __init__(self):
        super().__init__()
        self.parts = []

    async def process_frame(self, frame: Frame, direction):
        if isinstance(frame, UserTranscriptionFrame):
            text = frame.text.strip()
            if text:
                self.parts.append(f"Owner: {text}")
        elif isinstance(frame, TextFrame):
            text = frame.text.strip()
            if text:
                self.parts.append(f"Agent: {text}")
        await self.push_frame(frame, direction)

    def get_transcript(self) -> str:
        return "\n".join(self.parts)


def extract_outcome(transcript: str) -> str:
    text = transcript.lower()
    outcomes = ["interested", "callback", "pitched", "not interested"]
    last_idx = -1
    detected = "not interested"
    for o in outcomes:
        idx = text.rfind(o)
        if idx > last_idx:
            last_idx = idx
            detected = o
    return {
        "interested": "Interested",
        "callback": "Callback",
        "pitched": "Pitched",
        "not interested": "Not interested",
    }.get(detected, "Not interested")


# ── Bot Pipeline ─────────────────────────────────────────────────────────────

async def run_bot(
    transport: FastAPIWebsocketTransport,
    body_data: dict,
    call_id: str,
):
    """Build and run the full voice AI pipeline for one outbound call."""

    business_name = body_data.get("business_name", "the business")
    business_type = body_data.get("business_type", "local business")
    logger.info(f"[{call_id[:8]}] Starting call for {business_name} ({business_type})")

    # ── LLM ──────────────────────────────────────────────────────────────
    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model="gemini-2.0-flash-live",
    )

    # ── STT ──────────────────────────────────────────────────────────────
    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        params=DeepgramSTTService.InputParams(
            language="en-US",
            smart_format=True,
            punctuate=True,
            interim_results=False,
        ),
    )

    # ── TTS ──────────────────────────────────────────────────────────────
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
    )

    # ── Context & Aggregators ────────────────────────────────────────────
    context = LLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT.format(
            business_name=business_name,
            business_type=business_type,
        )}]
    )

    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # ── Transcript Accumulator ────────────────────────────────────────────
    transcript_acc = TranscriptAccumulator()

    # ── Pipeline ─────────────────────────────────────────────────────────
    pipeline = Pipeline([
        transport.input(),
        stt,
        user_agg,
        transcript_acc,
        llm,
        assistant_agg,
        tts,
        transport.output(),
    ])

    # ── Worker ───────────────────────────────────────────────────────────
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    start_time = time.time()

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info(f"[{call_id[:8]}] Call connected — starting conversation")

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info(f"[{call_id[:8]}] Call disconnected — ending pipeline")
        await worker.cancel()

    try:
        await worker.run()
    except asyncio.CancelledError:
        logger.info(f"[{call_id[:8]}] Pipeline cancelled")
    except Exception as e:
        logger.error(f"[{call_id[:8]}] Pipeline error: {e}")
    finally:
        duration = max(1, int(time.time() - start_time))
        transcript = transcript_acc.get_transcript()
        outcome = extract_outcome(transcript)
        logger.info(f"[{call_id[:8]}] Outcome: {outcome} | Duration: {duration}s")

        recording_path = save_recording(call_id)
        post_result(call_id, body_data, transcript, outcome, duration, recording_path)


def save_recording(call_id: str) -> str:
    """Write a placeholder WAV file. Real audio capture uses audio buffer frames."""
    recordings_dir = os.environ.get("RECORDINGS_DIR", "/recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    path = os.path.join(recordings_dir, f"{call_id}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 32000)
    return f"recordings/{call_id}.wav"


def post_result(
    call_id: str,
    body_data: dict,
    transcript: str,
    outcome: str,
    duration: int,
    recording_path: str,
):
    """POST call result to the backend."""
    import httpx

    backend_url = os.getenv("BACKEND_URL", "").rstrip("/")
    if not backend_url:
        logger.warning(f"[{call_id[:8]}] BACKEND_URL not set — skipping result POST")
        return

    payload = {
        "business_name": body_data.get("business_name", "Unknown"),
        "phone_number": body_data.get("phone_number", "Unknown"),
        "business_type": body_data.get("business_type", "Unknown"),
        "duration_seconds": duration,
        "outcome": outcome,
        "transcript": transcript,
        "recording_path": recording_path,
    }

    try:
        with httpx.SyncClient(timeout=15) as client:
            resp = client.post(f"{backend_url}/calls", json=payload)
            if resp.status_code in (200, 201):
                logger.info(f"[{call_id[:8]}] Result posted to backend")
            else:
                logger.warning(f"[{call_id[:8]}] POST failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"[{call_id[:8]}] POST error: {e}")


# ── Entry Point ─────────────────────────────────────────────────────────────

async def bot(runner_args: RunnerArguments):
    """
    Called by server.py when Telnyx opens a WebSocket connection.
    Auto-detects Telnyx transport, configures serializer + transport, runs pipeline.
    """
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(f"Detected transport: {transport_type} | call_data: {call_data}")

    serializer = TelnyxFrameSerializer(
        stream_id=call_data["stream_id"],
        outbound_encoding=call_data.get("outbound_encoding", "PCMU"),
        inbound_encoding="PCMU",
        call_control_id=call_data.get("call_control_id"),
        api_key=os.getenv("TELNYX_API_KEY"),
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    call_id = str(uuid.uuid4())
    await run_bot(transport, runner_args.body or {}, call_id)
