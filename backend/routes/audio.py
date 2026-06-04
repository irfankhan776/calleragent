import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from database import get_session
from models import Call

router = APIRouter(prefix="/calls", tags=["audio"])


@router.get("/{call_id}/audio")
def get_call_audio(call_id: str, session: Session = Depends(get_session)):
    call = session.get(Call, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    recording_path = call.recording_path
    if not recording_path:
        raise HTTPException(status_code=404, detail="No recording path associated with this call")

    recordings_dir = os.environ.get("RECORDINGS_DIR", "/app/recordings")

    filename = os.path.basename(recording_path)
    file_path = os.path.join(recordings_dir, filename)

    if not os.path.exists(file_path):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fallback_path = os.path.join(root_dir, recording_path.lstrip("./"))
        if os.path.exists(fallback_path):
            file_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail=f"Audio file not found: {filename}")

    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=filename,
    )
