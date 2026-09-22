"""Foundation tests: config loads, app boots, probes respond."""
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.main import app

client = TestClient(app)


def test_settings_load():
    s = get_settings()
    assert s.APP_NAME == "hr-policy-rag"
    assert s.QDRANT_COLLECTION == "hr_policies"
    # Values may come from .env — assert validity, not exact defaults.
    assert s.EMBED_DIM in (1024, 1536) and s.EMBED_MODEL
    assert s.CHUNK_SIZE == 512 and s.CHUNK_OVERLAP == 64


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_reports_all_deps():
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["checks"].keys() == {"postgres", "qdrant", "redis"}
    assert body["status"] in ("ready", "degraded")


def test_openapi_exposed():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/health" in r.json()["paths"]
