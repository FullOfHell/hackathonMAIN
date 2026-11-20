import httpx
import pytest

from app.api import extract
from app.integrations import transcription


PATH = "/api/intake/transcription"
AUDIO = b"synthetic test audio"
HEADERS = {"Content-Type": "audio/webm;codecs=opus"}


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-api-token")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe")


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "OPENAI_TRANSCRIPTION_MODEL"])
def test_transcription_requires_both_settings(client, configured, monkeypatch, missing):
    monkeypatch.setenv(missing, "")
    assert client.get(PATH).json() == {"enabled": False}
    assert client.post(PATH, content=AUDIO, headers=HEADERS).status_code == 503


def test_audio_is_forwarded_for_transcription_without_creating_a_case(client, configured, monkeypatch):
    async def provider(_client, url, *, headers, files, data):
        assert url == "https://api.openai.com/v1/audio/transcriptions"
        assert headers == {"Authorization": "Bearer test-only-api-token"}
        assert files == {"file": ("report.webm", AUDIO, "audio/webm")}
        assert data == {"model": "gpt-transcribe"}
        return httpx.Response(200, json={"text": " The upstairs radiators are cold. "}, request=httpx.Request("POST", url))

    monkeypatch.setattr(transcription.httpx.AsyncClient, "post", provider)
    before = client.get("/api/units/unit_4b/cases").json()
    assert client.get(PATH).json() == {"enabled": True}
    response = client.post(PATH, content=AUDIO, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"text": "The upstairs radiators are cold."}
    assert client.get("/api/units/unit_4b/cases").json() == before
    assert client.get("/partners/heatfix/connector/jobs").json() == []


def test_empty_oversized_and_unsupported_recordings_are_rejected(client, configured, monkeypatch):
    monkeypatch.setattr(extract, "MAX_RECORDING_BYTES", 10)
    assert client.post(PATH, content=b"", headers=HEADERS).status_code == 422
    assert client.post(PATH, content=AUDIO, headers=HEADERS).status_code == 413
    assert client.post(PATH, content=AUDIO, headers={"Content-Type": "text/plain"}).status_code == 415


@pytest.mark.parametrize(("status", "body", "expected"), [
    (401, {"error": "private provider detail"}, 502),
    (200, {"unexpected": True}, 502),
    (200, {"text": " "}, 422),
])
def test_provider_errors_and_blank_transcripts_offer_a_recoverable_error(
    client, configured, monkeypatch, status, body, expected,
):
    async def provider(_client, url, **_options):
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(transcription.httpx.AsyncClient, "post", provider)
    response = client.post(PATH, content=AUDIO, headers=HEADERS)
    assert response.status_code == expected
    assert "private provider detail" not in response.text
