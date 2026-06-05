"""
runtime.py

SmartReception Agent-Web — Realtime Voice AI Service

Replaces the Pipecat-based server.py + bot.py combo.
Uses direct Telnyx media streaming WebSocket + Deepgram STT + Gemini Realtime + ElevenLabs TTS.

Audio pipeline per call:
  Telnyx (8kHz μ-law)  →  decode  →  upsample 16kHz  →  Deepgram STT
                                                         →  Gemini Live API
                                                        ←  Gemini audio (24kHz PCM16)
                                                   downsample  →  encode μ-law  →  Telnyx
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import struct
import time
from dataclasses import dataclass, field

import httpx

try:
    import audioop
    _HAS_AUDIOOP = True
except ImportError:
    _HAS_AUDIOOP = False

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agent-runtime")


# ── Config ────────────────────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/") or "http://localhost:8000"


# ── System Prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Mia, a warm, professional, and highly effective AI sales representative for SmartReception — an AI-powered phone receptionist service for local businesses.

You are calling {business_name}, a {business_type} in their local area.

## Your Persona
- Confident but never pushy. You sound like a knowledgeable local business owner, not a telemarketer.
- You speak in a friendly, conversational tone — like talking to a neighbor.
- You're brief. Every response is 1-2 short sentences max. NEVER ramble.
- You're honest. If they say they have a solution, acknowledge it warmly.

## Opening (say this first)
"Hi, is this {business_name}? Great — I'm Mia calling from SmartReception. We just helped a {business_type} nearby handle their calls 24/7 with our AI receptionist — it answers, books appointments, and handles follow-ups automatically. Do you have 60 seconds?"

## Conversation Flow

### If they say YES / show interest:
"So instead of missing calls when you're with a customer, our AI picks up instantly, sounds completely natural, books appointments straight into your calendar, and you get a text summary of every conversation. It's $99 a month flat — no per-minute charges."
"If they want a demo: Love that! I can set up a quick 15-minute call where you can actually hear it in action — what day works best this week?"
"If they want to think about it: Totally fair. I'll send you a quick text with a short video demo so you can see it in 90 seconds. What's the best number to reach you?"

### If they say they're BUSY / in a rush:
"Completely understand — I'll be quick. Do you ever miss calls when you're with a customer?"
"If yes: That's actually really common. Our AI handles those exact moments. Can I call you back tomorrow afternoon?"
"If no: That's great — but do you ever get home and realize you forgot to call someone back? That's what we solve too. Can I send you a quick text with more info?"

### If they say NO / not interested:
"No worries at all — totally understand. Quick question: do you ever wish you had five more minutes in the day?"
"If yes: That's exactly what our clients say. Here's a thought — what if your phone could handle the simple stuff so you only got interrupted for the important stuff? Want me to send you a 60-second demo video?"
"If no: Alright, I really appreciate your time today. Have a great one!"

## Hard Rules
1. NEVER be pushy, aggressive, or argue.
2. NEVER talk for more than 2 sentences without inviting a response.
3. NEVER read from a script — sound natural.
4. At the VERY END of the call, say EXACTLY one word as your final word: Interested, Callback, Pitched, or Not_interested.
5. Always try to get a callback appointment or email before ending.
6. If the person is rude, thank them warmly and end gracefully.
"""


# ── Call Session ──────────────────────────────────────────────────────────────

@dataclass
class CallSession:
    call_id: str
    business_name: str
    business_type: str
    phone_number: str
    started_at: float = field(default_factory=time.time)
    transcript_parts: list[str] = field(default_factory=list)
    ended: bool = False
    disconnect_reason: str = "unknown"

    def add_user(self, text: str):
        if text.strip():
            self.transcript_parts.append(f"Owner: {text.strip()}")

    def add_agent(self, text: str):
        if text.strip():
            self.transcript_parts.append(f"Agent: {text.strip()}")

    def get_transcript(self) -> str:
        return "\n".join(self.transcript_parts)

    def duration(self) -> int:
        return max(1, int(time.time() - self.started_at))


# ── Session Registry ─────────────────────────────────────────────────────────
_sessions: dict[str, CallSession] = {}
_session_lock = asyncio.Lock()


# ── Audio Utilities ───────────────────────────────────────────────────────────

def ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
    """Convert μ-law (8kHz) to 16-bit PCM."""
    if _HAS_AUDIOOP:
        return audioop.ulaw2lin(ulaw_bytes, 2)
    # Fallback: decode manually
    result = bytearray()
    for byte in ulaw_bytes:
        uval = byte ^ 0xFF if byte != 0 else 0x80
        sign = uval & 0x80
        exponent = (uval >> 4) & 0x07
        mantissa = uval & 0x0F
        decoded = (mantissa << 3) + 132
        decoded <<= exponent
        result.extend(struct.pack("<h", -decoded if sign else decoded))
    return bytes(result)


def pcm16_to_ulaw(pcm16_bytes: bytes) -> bytes:
    """Convert 16-bit PCM to μ-law (8kHz)."""
    if _HAS_AUDIOOP:
        return audioop.lin2ulaw(pcm16_bytes, 2)
    # Fallback: encode manually
    result = bytearray()
    for i in range(0, len(pcm16_bytes), 2):
        s = struct.unpack_from("<h", pcm16_bytes, i)[0]
        sign = 0
        if s < 0:
            sign = 0x80
            s = -s
        s += 132
        if s > 8159:
            s = 8159
        exponent = 7
        for e in range(7):
            if s <= (132 << e):
                exponent = max(0, e - 1)
                break
        mantissa = (s - (132 << exponent)) >> 2
        encoded = (sign | (exponent << 4) | mantissa) ^ 0xFF
        result.append(encoded)
    return bytes(result)


def resample(PCM16_bytes: bytes, orig_rate: int, new_rate: int) -> bytes:
    """
    Simple linear-interpolation resampling between sample rates.
    Handles 16-bit signed little-endian PCM.
    """
    if orig_rate == new_rate or not PCM16_bytes:
        return PCM16_bytes

    n_samples = len(PCM16_bytes) // 2
    ratio = new_rate / orig_rate
    new_n = max(1, int(n_samples * ratio))

    result = bytearray(new_n * 2)
    for i in range(new_n):
        pos = i / ratio
        idx = int(pos)
        frac = pos - idx
        idx = min(idx, n_samples - 1)
        nidx = min(idx + 1, n_samples - 1)
        s1 = struct.unpack_from("<h", PCM16_bytes, idx * 2)[0]
        s2 = struct.unpack_from("<h", PCM16_bytes, nidx * 2)[0]
        s = int(s1 + frac * (s2 - s1))
        s = max(-32768, min(32767, s))
        struct.pack_into("<h", result, i * 2, s)

    return bytes(result)


# ── Outcome extraction ────────────────────────────────────────────────────────

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


# ── Backend Result Reporting ───────────────────────────────────────────────────

async def report_result_to_backend(session: CallSession):
    """POST the completed call result to the backend."""
    url = f"{BACKEND_URL}/calls"
    payload = {
        "business_name": session.business_name,
        "phone_number": session.phone_number,
        "business_type": session.business_type,
        "duration_seconds": session.duration(),
        "outcome": extract_outcome(session.get_transcript()),
        "transcript": session.get_transcript(),
        "recording_path": f"recordings/{session.call_id}.wav",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in (200, 201):
                log.info(f"[{session.call_id[:8]}] Result posted to backend")
            else:
                log.warning(
                    f"[{session.call_id[:8]}] Backend POST failed: "
                    f"{resp.status_code} {resp.text}"
                )
    except Exception as e:
        log.warning(f"[{session.call_id[:8]}] Backend POST error: {e}")


# ── Telnyx Frame Utilities ────────────────────────────────────────────────────

def parse_telnyx_frame(raw: bytes) -> dict | None:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def build_telnyx_media_frame(payload_b64: str) -> bytes:
    frame = {
        "event": "media",
        "media": {
            "track": "inbound_track",
            "payload": payload_b64,
            "timestamp": int(time.time() * 1000),
        },
    }
    return json.dumps(frame).encode("utf-8")


# ── Per-Session WebSocket Handler ────────────────────────────────────────────

async def handle_stream_websocket(websocket, call_id: str, body_data: dict):
    """
    Handles one inbound Telnyx WebSocket session (one call).

    Telnyx opens this WS after the outbound call is answered.
    We receive μ-law RTP audio (8kHz), convert and forward to Deepgram + Gemini,
    then stream audio responses back.
    """
    session = CallSession(
        call_id=call_id,
        business_name=body_data.get("business_name", "the business"),
        business_type=body_data.get("business_type", "local business"),
        phone_number=body_data.get("phone_number", ""),
    )
    call_control_id = body_data.get("call_control_id", "")

    async with _session_lock:
        _sessions[call_control_id] = session

    log.info(f"[{call_id[:8]}] WS connected — {session.business_name}")
    await websocket.accept()

    # ── Queues for async task coordination ──────────────────────────────────
    telnyx_in: asyncio.Queue[bytes] = asyncio.Queue()  # raw μ-law from Telnyx
    stop_event = asyncio.Event()
    stop_event.clear()

    # ── Deepgram STT (WebSocket) ───────────────────────────────────────────
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "")
    dg_live = None
    stt_queue: asyncio.Queue[str] = asyncio.Queue()
    dg_task: asyncio.Task | None = None

    if deepgram_key:
        try:
            from deepgram import AsyncDeepgramClient
            from deepgram.core.events import EventType

            dg_client = AsyncDeepgramClient(deepgram_key)

            async def on_dg_message(result, **kwargs):
                msg_type = getattr(result, "type", "")
                if msg_type == "Results":
                    if hasattr(result, "channel") and result.channel:
                        for alt in getattr(result.channel, "alternatives", []):
                            text = getattr(alt, "transcript", "").strip()
                            if text:
                                await stt_queue.put(text)

            # v6 listen.v2: mulaw encoding, 8kHz — direct passthrough from Telnyx
            async with dg_client.listen.v2.connect(
                model="flux-general-en",
                language="en",
                smart_format=True,
                punctuate=True,
                interim_results=False,
                encoding="mulaw",
                sample_rate=8000,
                channels=1,
            ) as dg_live:
                dg_live.on(EventType.MESSAGE, on_dg_message)
                await dg_live.start_listening()

                async def dg_forward_loop():
                    while not stop_event.is_set():
                        try:
                            raw_ulaw = await asyncio.wait_for(telnyx_in.get(), timeout=1.0)
                            # Telnyx μ-law 8kHz passes directly to Deepgram v2
                            await dg_live.send(raw_ulaw)
                        except asyncio.TimeoutError:
                            pass
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            log.warning(f"Deepgram send error: {e}")

                dg_task = asyncio.create_task(dg_forward_loop())
                log.info(f"[{call_id[:8]}] Deepgram STT started (v2, mulaw, 8kHz)")

                # Wait for stop, then signal task to end
                await stop_event.wait()
                dg_task.cancel()
                try:
                    await dg_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            log.warning(f"[{call_id[:8]}] Deepgram init failed: {e} — continuing without STT")

    # ── Gemini Live Session ────────────────────────────────────────────────
    api_key = os.getenv("GOOGLE_API_KEY", "")
    gemini_session = None
    gemini_tasks: list[asyncio.Task] = []

    if api_key:
        try:
            from google import genai
            from google.genai import types

            genai.configure(api_key=api_key)

            config = types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                system_instruction=types.Content(
                    role="system",
                    parts=[types.Part(text=SYSTEM_PROMPT.format(
                        business_name=session.business_name,
                        business_type=session.business_type,
                    ))],
                ),
            )

            client = genai.Client(api_key=api_key)

            async with client.aio.live.connect(
                model="gemini-3.1-flash-live-preview",
                config=config,
            ) as gemini_session:
                log.info(f"[{call_id[:8]}] Gemini Live session connected")

                # Task: forward Deepgram STT transcripts to Gemini
                async def gemini_stt_forward():
                    while not stop_event.is_set():
                        try:
                            text = await asyncio.wait_for(stt_queue.get(), timeout=20.0)
                            session.add_user(text)
                            await gemini_session.send_realtime_input(
                                text=text
                            )
                        except asyncio.TimeoutError:
                            continue
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            log.warning(f"Gemini send error: {e}")
                            break

                # Task: receive Gemini audio + transcription, send back to Telnyx
                async def gemini_recv_loop():
                    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
                    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
                    elevenlabs_client = None
                    if elevenlabs_key:
                        try:
                            from elevenlabs.client import ElevenLabs
                            elevenlabs_client = ElevenLabs(api_key=elevenlabs_key)
                        except Exception as e:
                            log.warning(f"ElevenLabs init failed: {e}")

                    while not stop_event.is_set():
                        try:
                            async for response in gemini_session.receive():
                                server = getattr(response, "server_content", None)
                                if not server:
                                    continue

                                # Transcription of user speech
                                inp = getattr(server, "input_transcription", None)
                                if inp and hasattr(inp, "text") and inp.text:
                                    session.add_user(inp.text)

                                # Transcription of agent speech
                                outp = getattr(server, "output_transcription", None)
                                if outp and hasattr(outp, "text") and outp.text:
                                    session.add_agent(outp.text)

                                # Audio from Gemini
                                mt = getattr(server, "model_turn", None)
                                if mt:
                                    for part in getattr(mt, "parts", []):
                                        inline = getattr(part, "inline_data", None)
                                        if not inline:
                                            text_part = getattr(part, "text", None)
                                            if text_part and elevenlabs_client and voice_id:
                                                # Fallback: TTS via ElevenLabs
                                                session.add_agent(text_part)
                                                try:
                                                    audio_bytes = b""
                                                    async for chunk in elevenlabs_client.text_to_speech.convert_asynchronously(
                                                        voice_id=voice_id,
                                                        text=text_part,
                                                        model_id="eleven_multilingual",
                                                        output_format="pcm_22050",
                                                    ):
                                                        audio_bytes += chunk
                                                    # Convert 22050Hz PCM16 → 8000Hz μ-law → Telnyx
                                                    pcm8 = resample(audio_bytes, 22050, 8000)
                                                    ulaw_out = pcm16_to_ulaw(pcm8)
                                                    if ulaw_out:
                                                        await websocket.send_bytes(
                                                            build_telnyx_media_frame(
                                                                base64.b64encode(ulaw_out).decode()
                                                            )
                                                        )
                                                except Exception as e:
                                                    log.warning(f"ElevenLabs TTS error: {e}")
                                            continue

                                        # Process Gemini audio output (24kHz PCM16 base64)
                                        mime = getattr(inline, "mime_type", "")
                                        data_bytes_b64 = getattr(inline, "data", "")
                                        if not data_bytes_b64:
                                            continue

                                        try:
                                            audio_pcm = base64.b64decode(data_bytes_b64)
                                        except Exception:
                                            continue

                                        # Convert 24kHz PCM16 → 8kHz μ-law for Telnyx
                                        pcm8 = resample(audio_pcm, 24000, 8000)
                                        ulaw_out = pcm16_to_ulaw(pcm8)
                                        if ulaw_out:
                                            try:
                                                await websocket.send_bytes(
                                                    build_telnyx_media_frame(
                                                        base64.b64encode(ulaw_out).decode()
                                                    )
                                                )
                                            except Exception as e:
                                                log.warning(f"Telnyx send error: {e}")

                                # Interruption / turn complete
                                if getattr(server, "turn_complete", False):
                                    pass

                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            log.warning(f"Gemini recv error: {e}")
                            break

                gemini_tasks = [
                    asyncio.create_task(gemini_stt_forward()),
                    asyncio.create_task(gemini_recv_loop()),
                ]

                # ── Main read loop: Telnyx → telnyx_in queue ──────────────────
                async def read_loop():
                    try:
                        async for raw in websocket.iter_bytes():
                            frame = parse_telnyx_frame(raw)
                            if frame is None:
                                continue

                            event = frame.get("event")

                            if event == "media":
                                payload_b64 = frame.get("media", {}).get("payload", "")
                                if payload_b64:
                                    try:
                                        await telnyx_in.put(base64.b64decode(payload_b64))
                                    except Exception:
                                        pass

                            elif event == "start":
                                log.info(f"[{call_id[:8]}] Stream started: {frame.get('start')}")

                            elif event == "stop":
                                log.info(f"[{call_id[:8]}] Stream stopped")
                                stop_event.set()
                                break

                            elif event in ("dtmf", "mark", "info"):
                                pass

                            elif event == "error":
                                log.warning(f"[{call_id[:8]}] Telnyx error: {frame}")

                    except asyncio.CancelledError:
                        stop_event.set()
                    except Exception as e:
                        log.warning(f"[{call_id[:8]}] Read error: {e}")
                        stop_event.set()

                await read_loop()

        except Exception as e:
            log.error(f"[{call_id[:8]}] Gemini init failed: {e}", exc_info=True)
            gemini_session = None

    # ── Cleanup ─────────────────────────────────────────────────────────────
    stop_event.set()

    for task in gemini_tasks:
        task.cancel()
    await asyncio.gather(*gemini_tasks, return_exceptions=True)

    if dg_task:
        dg_task.cancel()
        await asyncio.gather(dg_task, return_exceptions=True)

    if dg_live:
        try:
            dg_live.send_close_stream()
        except Exception:
            pass

    if gemini_session:
        try:
            await gemini_session.close()
        except Exception:
            pass

    session.ended = True
    session.disconnect_reason = "stream_closed"

    # ── Post result to backend ─────────────────────────────────────────────
    await report_result_to_backend(session)

    async with _session_lock:
        _sessions.pop(call_control_id, None)

    log.info(f"[{call_id[:8]}] Session done — {session.get_transcript()[:120]}")
