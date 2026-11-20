import httpx
from fastapi import APIRouter, HTTPException, Request

from app.integrations.transcription import transcribe_audio, transcription_config
from app.schemas import IntakeRequest, IntakeResponse
from app.services.intake import extract


router = APIRouter(prefix="/api/intake", tags=["intake"])
MAX_RECORDING_BYTES = 4 * 1024 * 1024
RECORDING_FORMATS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a"}


@router.post("/extract", response_model=IntakeResponse)
def extract_intake(draft: IntakeRequest) -> IntakeResponse:
    return extract(draft)


@router.get("/transcription")
def transcription_status() -> dict[str, bool]:
    return {"enabled": transcription_config() is not None}


@router.post("/transcription")
async def transcribe_report(request: Request) -> dict[str, str]:
    config = transcription_config()
    if not config:
        raise HTTPException(503, "Voice input is unavailable. You can type your report.")

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    extension = RECORDING_FORMATS.get(media_type)
    if extension is None:
        raise HTTPException(415, "This recording format is unsupported. You can type your report.")
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_RECORDING_BYTES:
            raise HTTPException(413, "This recording is too large. Try a shorter clip.")
        audio.extend(chunk)
    if not audio:
        raise HTTPException(422, "The recording is empty. Try recording again.")

    try:
        text = await transcribe_audio(bytes(audio), media_type, extension, config)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Transcription failed. Retry or type your report.") from None
    if not text:
        raise HTTPException(422, "No speech was recognized. Try recording again.")
    return {"text": text}
