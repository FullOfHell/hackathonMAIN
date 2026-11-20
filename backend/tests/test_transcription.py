import httpx
import pytest

from app.api import extract
from app.integrations import transcription


PATH = "/api/intake/transcription"
AUDIO = b"synthetic test audio"
HEADERS = {"Content-Type": "audio/webm;codecs=opus"}


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-api-token")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-elevenlabs-token")


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "OPENAI_TRANSCRIPTION_MODEL"])
def test_transcription_requires_both_settings(client, configured, monkeypatch, missing):
    monkeypatch.setenv(missing, "")
    assert client.get(PATH).json() == {"enabled": False}
    assert client.post(PATH, content=AUDIO, headers=HEADERS).status_code == 503


@pytest.mark.parametrize(("selected", "expected_url", "expected_headers", "expected_data"), [
    ("", "https://api.openai.com/v1/audio/transcriptions",
     {"Authorization": "Bearer test-only-api-token"}, {"model": "gpt-transcribe"}),
    ("elevenlabs", "https://api.elevenlabs.io/v1/speech-to-text",
     {"xi-api-key": "test-only-elevenlabs-token"}, {"model_id": "scribe_v2"}),
])
def test_audio_is_forwarded_for_transcription_without_creating_a_case(
    client, configured, monkeypatch, selected, expected_url, expected_headers, expected_data,
):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", selected)
    if selected == "elevenlabs":
        monkeypatch.setenv("OPENAI_API_KEY", "")
        monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "")

    async def provider(_client, url, *, headers, files, data):
        assert url == expected_url
        assert headers == expected_headers
        assert files == {"file": ("report.webm", AUDIO, "audio/webm")}
        assert data == expected_data
        return httpx.Response(200, json={"text": " The upstairs radiators are cold. "}, request=httpx.Request("POST", url))

    monkeypatch.setattr(transcription.httpx.AsyncClient, "post", provider)
    before = client.get("/api/units/unit_4b/cases").json()
    assert client.get(PATH).json() == {"enabled": True}
    response = client.post(PATH, content=AUDIO, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"text": "The upstairs radiators are cold."}
    assert client.get("/api/units/unit_4b/cases").json() == before
    assert client.get("/partners/heatfix/connector/jobs").json() == []


@pytest.mark.parametrize("selected", ["elevenlabs", "unknown"])
def test_unconfigured_provider_does_not_send_audio_or_fall_back_to_openai(client, configured, monkeypatch, selected):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", selected)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")

    async def unexpected_request(*_args, **_kwargs):
        pytest.fail("audio must stay local when the selected provider is unavailable")

    monkeypatch.setattr(transcription.httpx.AsyncClient, "post", unexpected_request)
    assert client.get(PATH).json() == {"enabled": False}
    assert client.post(PATH, content=AUDIO, headers=HEADERS).status_code == 503


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
@pytest.mark.parametrize("selected", ["openai", "elevenlabs"])
def test_provider_errors_and_blank_transcripts_offer_a_recoverable_error(
    client, configured, monkeypatch, selected, status, body, expected,
):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", selected)

    async def provider(_client, url, **_options):
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(transcription.httpx.AsyncClient, "post", provider)
    response = client.post(PATH, content=AUDIO, headers=HEADERS)
    assert response.status_code == expected
    assert "private provider detail" not in response.text


def test_elevenlabs_timeout_preserves_manual_entry(client, configured, monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "elevenlabs")

    async def provider(_client, url, **_options):
        assert url == "https://api.elevenlabs.io/v1/speech-to-text"
        raise httpx.ReadTimeout("private provider detail")

    monkeypatch.setattr(transcription.httpx.AsyncClient, "post", provider)
    response = client.post(PATH, content=AUDIO, headers=HEADERS)
    assert response.status_code == 502
    assert response.json() == {"detail": "Transcription failed. Retry or type your report."}
