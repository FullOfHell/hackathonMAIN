import os

import httpx


def transcription_config() -> tuple[str, str, str] | None:
    provider = os.getenv("TRANSCRIPTION_PROVIDER", "").strip().lower() or "openai"
    if provider == "elevenlabs":
        key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        model = "scribe_v2"
    elif provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "").strip()
    else:
        return None
    return (provider, key, model) if key and model else None


async def transcribe_audio(audio: bytes, media_type: str, extension: str, config: tuple[str, str, str]) -> str:
    provider, key, model = config
    if provider == "elevenlabs":
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": key}
        data = {"model_id": model}
    else:
        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {key}"}
        data = {"model": model}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            url,
            headers=headers,
            files={"file": (f"report.{extension}", audio, media_type)},
            data=data,
        )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        raise ValueError("Invalid transcription response")
    return text.strip()
