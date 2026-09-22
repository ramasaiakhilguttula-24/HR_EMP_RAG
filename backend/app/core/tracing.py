"""LangSmith tracing glue (Feature 16).

Our `traceable` wraps langsmith's decorator but bypasses it entirely when tracing
is disabled or no key is configured — zero network, zero test pollution. Toggle:
LANGSMITH_TRACING=false or empty LANGSMITH_API_KEY.
"""
from functools import wraps

from backend.app.core.config import get_settings

_client = None


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.LANGSMITH_TRACING and s.LANGSMITH_API_KEY)


def _ensure_env() -> bool:
    """Export SDK env vars from our Settings (the SDK is env-driven)."""
    import os

    s = get_settings()
    if not s.LANGSMITH_API_KEY:
        return False
    os.environ.setdefault("LANGSMITH_API_KEY", s.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGSMITH_PROJECT", s.LANGSMITH_PROJECT)
    os.environ.setdefault("LANGSMITH_TRACING", "true" if s.LANGSMITH_TRACING else "false")
    return True


def get_client():
    """LangSmith client or None (no key). Never raises."""
    global _client
    if not _ensure_env():
        return None
    if _client is None:
        try:
            from langsmith import Client

            _client = Client(api_key=get_settings().LANGSMITH_API_KEY)
        except Exception:
            return None
    return _client


def traceable(name: str | None = None, run_type: str = "chain"):
    """Decorator: full LangSmith run when enabled, plain call otherwise."""
    def deco(fn):
        try:
            from langsmith import traceable as _ls_traceable

            traced = _ls_traceable(fn, name=name or fn.__name__, run_type=run_type)
        except Exception:
            traced = None

        @wraps(fn)
        def inner(*args, **kwargs):
            if not is_enabled() or traced is None:
                return fn(*args, **kwargs)
            _ensure_env()
            return traced(*args, **kwargs)

        inner._rag_trace_name = name or fn.__name__
        return inner

    return deco


def log_feedback(run_id: str, score: int) -> bool:
    """Attach thumbs up/down to a LangSmith run. False when unavailable."""
    client = get_client()
    if client is None or not run_id:
        return False
    try:
        client.create_feedback(run_id, key="thumbs", score=float(score),
                               value="up" if score > 0 else "down")
        return True
    except Exception:
        return False
