import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    from app.integrations.connector import get_partner_client
    from app.main import app

    with TestClient(app) as c:
        app.dependency_overrides[get_partner_client] = lambda: c  # partner calls go in-process
        yield c
        app.dependency_overrides.clear()
