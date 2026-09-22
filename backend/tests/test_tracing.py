"""Tracing tests: disabled bypass, decorator transparency, feedback endpoint."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.core import tracing
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.main import app
from backend.app.models.user import User, UserRole


def test_disabled_bypasses_langsmith(monkeypatch):
    assert tracing.is_enabled() is False  # conftest forces OFF

    called = {}

    def fn(x):
        called["x"] = x
        return x * 2

    wrapped = tracing.traceable(name="t", run_type="chain")(fn)
    assert wrapped(21) == 42 and called == {"x": 21}
    assert getattr(wrapped, "_rag_trace_name", None) == "t"


def test_get_client_none_without_key(monkeypatch):
    monkeypatch.setattr("backend.app.core.tracing.get_settings",
                        lambda: type("S", (), {"LANGSMITH_API_KEY": ""})())
    tracing._client = None
    assert tracing.get_client() is None


def test_log_feedback_false_without_client():
    assert tracing.log_feedback("", 1) is False
    assert tracing.log_feedback("some-id", 1) is False  # no key in test env


def _api_client(single=None):
    import uuid

    user = User(email="e@c.com", password_hash="x", full_name="E", role=UserRole.employee)
    user.id = uuid.uuid4()
    user.is_active = True
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=lambda: single)
    session.add = MagicMock(return_value=None)
    session.commit.return_value = None

    async def _db():
        yield session

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), session


def teardown_function():
    app.dependency_overrides.clear()


def test_feedback_records_score():
    import uuid

    row = MagicMock(feedback=None)
    client, session = _api_client(single=row)
    r = client.post("/api/v1/feedback",
                    json={"query_log_id": str(uuid.uuid4()), "score": 1})
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "recorded", "langsmith_attached": False}
    assert row.feedback == 1
    session.commit.assert_called_once()


def test_feedback_404_and_validation():
    import uuid

    client, _ = _api_client(single=None)
    r = client.post("/api/v1/feedback", json={"query_log_id": str(uuid.uuid4()), "score": 1})
    assert r.status_code == 404
    r = client.post("/api/v1/feedback", json={"query_log_id": "nope", "score": 1})
    assert r.status_code == 422
    r = client.post("/api/v1/feedback", json={"query_log_id": str(uuid.uuid4()), "score": 5})
    assert r.status_code == 422
