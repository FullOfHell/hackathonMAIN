import os

import httpx


def transcription_config() -> tuple[str, str] | None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "").strip()
    return (key, model) if key and model else None


async def transcribe_audio(audio: bytes, media_type: str, extension: str, config: tuple[str, str]) -> str:
    key, model = config
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (f"report.{extension}", audio, media_type)},
            data={"model": model},
        )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        raise ValueError("Invalid transcription response")
    return text.strip()
