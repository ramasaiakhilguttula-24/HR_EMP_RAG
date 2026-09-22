"""Suite-wide: tracing stays OFF in tests (no LangSmith network/pollution)."""
import pytest

from backend.app.core import tracing


@pytest.fixture(autouse=True)
def _no_tracing(monkeypatch):
    monkeypatch.setattr(tracing, "is_enabled", lambda: False)
    monkeypatch.setattr(tracing, "_client", None)
    yield
