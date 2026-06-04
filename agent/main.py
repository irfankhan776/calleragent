import asyncio
import os
import uuid
import sys
import time
import random
import wave
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("pipecat-agent")

# ── Pipecat Imports ───────────────────────────────────────
try:
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask, PipelineParams
    from pipecat.services.google import GoogleLLMService
    from pipecat.services.deepgram import DeepgramSTTService
    from pipecat.services.elevenlabs import ElevenLabsTTSService
    from pipecat.transports.network.telnyx import TelnyxTransport, TelnyxParams
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
    from pipecat.processors.aggregators.llm_response import (
        LLMUserResponseAggregator,
        LLMAssistantResponseAggregator,
    )
    from pipecat.frames.frames import Frame, TextFrame, UserTranscriptionFrame
    from pipecat.processors.frame_processor import FrameProcessor
    PIPECAT_AVAILABLE = True
except ImportError as e:
    log.warning(f"Pipecat libraries not fully installed (Error: {e}). Using simulation mode.")
    PIPECAT_AVAILABLE = False

from pitch import SYSTEM_PROMPT
from webhooks import post_call_data


# ── Transcript Accumulator ───────────────────────────────

class TranscriptAccumulator:
    def __init__(self):
        self.transcript_parts = []

    def add_user(self, text: str):
        if text.strip():
            self.transcript_parts.append(f"Owner: {text.strip()}")

    def add_agent(self, text: str):
        if text.strip():
            self.transcript_parts.append(f"Agent: {text.strip()}")

    def get_transcript(self) -> str:
        return "\n".join(self.transcript_parts)


def extract_outcome(transcript: str) -> str:
    text = transcript.lower()
    outcomes = ["interested", "callback", "pitched", "not interested"]
    last_idx = -1
    detected = "Not interested"
    for o in outcomes:
        idx = text.rfind(o)
        if idx > last_idx:
            last_idx = idx
            detected = o
    mapping = {
        "interested": "Interested",
        "callback": "Callback",
        "pitched": "Pitched",
        "not interested": "Not interested",
    }
    return mapping.get(detected, "Not interested")


# ── Mock Call Generator ───────────────────────────────────

def generate_mock_call(business_name: str, business_type: str):
    outcomes = ["Interested", "Callback", "Pitched", "Not interested"]
    selected_outcome = random.choice(outcomes)
    transcript_accumulator = TranscriptAccumulator()

    opening = f"Hi, is this {business_name}? Great — quick question for you. We just finished building an AI receptionist for a {business_type} just down the road from you — answers calls, books appointments, handles follow-ups 24 hours a day. I wanted to see if it might help you guys too. Do you have literally 60 seconds?"
    transcript_accumulator.add_agent(opening)

    if selected_outcome == "Interested":
        transcript_accumulator.add_user("Yeah, actually, we do miss a lot of calls when we are busy. How does it work?")
        transcript_accumulator.add_agent("So basically instead of missing calls when you're busy, the AI picks up instantly, sounds completely human, handles bookings — and you get a dashboard showing every single call.")
        transcript_accumulator.add_user("Oh wow. How much does it cost?")
        transcript_accumulator.add_agent("It's a flat monthly fee — starts around $99 a month for unlimited calls. No per-minute charges. Most businesses make that back from one recovered booking.")
        transcript_accumulator.add_user("That sounds reasonable. I'd be open to seeing a demo.")
        transcript_accumulator.add_agent("Perfect! I can set up a quick 15-minute demo call so you can actually hear it in action. What does your week look like? Interested.")

    elif selected_outcome == "Callback":
        transcript_accumulator.add_user("We are actually in the middle of a rush right now. Can you call back later?")
        transcript_accumulator.add_agent("Totally understand — can I ask, do you ever miss calls when you're with a customer?")
        transcript_accumulator.add_user("Yes, all the time, but I really have to go. Call me tomorrow afternoon.")
        transcript_accumulator.add_agent("Will do! I'll call you back then. Have a great day! Callback.")

    elif selected_outcome == "Pitched":
        transcript_accumulator.add_user("Sure, tell me more.")
        transcript_accumulator.add_agent("So basically instead of missing calls when you're busy, the AI picks up instantly, sounds completely human, handles bookings — and you get a dashboard showing every single call.")
        transcript_accumulator.add_user("Hmm, we already have a receptionist, but sometimes she's away.")
        transcript_accumulator.add_agent("Exactly. We've already set it up for a similar business nearby and they said they stopped missing about 30 percent of their leads. It can back up your main receptionist.")
        transcript_accumulator.add_user("Okay, I'll think about it. Send me an email or something.")
        transcript_accumulator.add_agent("No problem, I can text you some info. Have a great day! Pitched.")

    else:
        transcript_accumulator.add_user("No thanks, we're not interested in any robot stuff.")
        transcript_accumulator.add_agent("Totally understand — can I ask, do you ever miss calls when you're with a customer?")
        transcript_accumulator.add_user("No, we answer everything. Please remove us from your list.")
        transcript_accumulator.add_agent("No worries at all — sorry to interrupt your day. Have a great one! Not interested.")

    duration = random.randint(15, 75)
    return transcript_accumulator.get_transcript(), selected_outcome, duration


# ── Live Pipecat Pipeline ─────────────────────────────────

async def run_pipecat_pipeline(
    business_name: str,
    phone_number: str,
    business_type: str,
    call_id: str
):
    required_keys = [
        "GOOGLE_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_ID", "TELNYX_API_KEY", "TELNYX_CONNECTION_ID", "TELNYX_FROM_NUMBER"
    ]
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")

    transport = TelnyxTransport(
        params=TelnyxParams(
            api_key=os.environ.get("TELNYX_API_KEY"),
            connection_id=os.environ.get("TELNYX_CONNECTION_ID"),
            from_number=os.environ.get("TELNYX_FROM_NUMBER"),
            to_number=phone_number,
            vad_analyzer=SileroVADAnalyzer(),
            audio_passthrough=True,
        )
    )

    stt = DeepgramSTTService(
        api_key=os.environ.get("DEEPGRAM_API_KEY"),
        params=DeepgramSTTService.InputParams(
            language="en-US",
            smart_format=True,
            punctuate=True,
            interim_results=False,
        )
    )

    llm = GoogleLLMService(
        api_key=os.environ.get("GOOGLE_API_KEY"),
        model="gemini-2.0-flash-live"
    )

    tts = ElevenLabsTTSService(
        api_key=os.environ.get("ELEVENLABS_API_KEY"),
        voice_id=os.environ.get("ELEVENLABS_VOICE_ID"),
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    recordings_dir = os.environ.get("RECORDINGS_DIR", os.path.join(project_root, "backend", "recordings"))
    os.makedirs(recordings_dir, exist_ok=True)
    recording_file = os.path.join(recordings_dir, f"{call_id}.wav")
    audio_buffer = AudioBufferProcessor()

    transcript_accumulator = TranscriptAccumulator()

    class TranscriptInterceptor(FrameProcessor):
        async def process_frame(self, frame: Frame, direction):
            if isinstance(frame, UserTranscriptionFrame):
                transcript_accumulator.add_user(frame.text)
            elif isinstance(frame, TextFrame):
                transcript_accumulator.add_agent(frame.text)
            await self.push_frame(frame, direction)

    interceptor = TranscriptInterceptor()

    formatted_prompt = SYSTEM_PROMPT.format(
        business_name=business_name,
        business_type=business_type
    )
    messages = [{"role": "system", "content": formatted_prompt}]
    user_aggregator = LLMUserResponseAggregator(messages)
    assistant_aggregator = LLMAssistantResponseAggregator(messages)

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        interceptor,
        llm,
        assistant_aggregator,
        tts,
        audio_buffer,
        transport.output()
    ])

    runner = PipelineRunner()
    task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))

    start_time = time.time()

    try:
        await runner.run([task])
    except asyncio.CancelledError:
        log.info(f"[{call_id[:8]}] Call ended.")
    except Exception as e:
        log.error(f"[{call_id[:8]}] Pipeline error: {e}")
        raise

    duration = max(1, int(time.time() - start_time))

    if hasattr(audio_buffer, "get_audio_data"):
        audio_data = audio_buffer.get_audio_data()
        if audio_data:
            with wave.open(recording_file, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_data)

    transcript = transcript_accumulator.get_transcript()
    outcome = extract_outcome(transcript)

    return transcript, outcome, duration


# ── Save Dummy Recording ──────────────────────────────────

def save_dummy_recording(call_id: str):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    recordings_dir = os.environ.get("RECORDINGS_DIR", os.path.join(project_root, "backend", "recordings"))
    os.makedirs(recordings_dir, exist_ok=True)
    recording_file = os.path.join(recordings_dir, f"{call_id}.wav")
    with wave.open(recording_file, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b'\x00' * 32000)
    return f"recordings/{call_id}.wav"


# ── Main Call Handler ──────────────────────────────────────

async def make_call(
    business_name: str,
    phone_number: str,
    business_type: str,
    dry_run: bool = False
) -> str:
    call_id = str(uuid.uuid4())
    log.info(f"[{call_id[:8]}] Starting call for {business_name} ({phone_number})")

    simulate = dry_run or not PIPECAT_AVAILABLE or not os.environ.get("TELNYX_API_KEY")

    if simulate:
        log.info(f"[{call_id[:8]}] SIMULATION mode active")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        transcript, outcome, duration = generate_mock_call(business_name, business_type)
        recording_path = save_dummy_recording(call_id)
    else:
        try:
            log.info(f"[{call_id[:8]}] Running LIVE Pipecat pipeline")
            transcript, outcome, duration = await run_pipecat_pipeline(
                business_name, phone_number, business_type, call_id
            )
            recording_path = f"recordings/{call_id}.wav"
        except Exception as e:
            log.error(f"[{call_id[:8]}] Pipeline error: {e}. Falling back to simulation.")
            transcript, outcome, duration = generate_mock_call(business_name, business_type)
            recording_path = save_dummy_recording(call_id)

    # POST results with retry
    for attempt in range(3):
        result = post_call_data(
            business_name=business_name,
            phone_number=phone_number,
            business_type=business_type,
            duration_seconds=duration,
            outcome=outcome,
            transcript=transcript,
            recording_path=recording_path
        )
        if result:
            log.info(f"[{call_id[:8]}] Call complete. Outcome: {outcome} | Posted successfully.")
            break
        wait = 2 ** attempt
        log.warning(f"[{call_id[:8]}] Post failed (attempt {attempt+1}/3). Retrying in {wait}s...")
        await asyncio.sleep(wait)
    else:
        log.error(f"[{call_id[:8]}] All post attempts failed. Outcome: {outcome}")

    return outcome


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python main.py [name] [phone] [type]")
        sys.exit(1)
    name = sys.argv[1]
    phone = sys.argv[2]
    btype = sys.argv[3]
    asyncio.run(make_call(name, phone, btype))
