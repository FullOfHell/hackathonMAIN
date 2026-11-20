import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    from app.integrations.connector import get_partner_client
    from app.main import app
    from app.partners.heatfix import get_callback_client

    monkeypatch.setenv("N8N_CASE_WEBHOOK_URL", "")
    monkeypatch.setenv("PARTNER_WEBHOOK_SECRET", "test-only-partner-secret")
    monkeypatch.setenv("PUBLIC_BACKEND_URL", "http://testserver")
    with TestClient(app) as c:
        app.dependency_overrides[get_partner_client] = lambda: c  # partner calls go in-process
        app.dependency_overrides[get_callback_client] = lambda: c
        try:
            yield c
        finally:
            app.dependency_overrides.clear()
