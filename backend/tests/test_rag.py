"""RAG pipeline tests: prompt/citations/fallback (faked) + SSE parsing + endpoints."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.main import app
from backend.app.models.user import User, UserRole
from backend.app.services.generation.rag_pipeline import (
    FALLBACK_MSG,
    MAX_CONTEXT_CHARS,
    answer_query,
    build_context,
    parse_sse_line,
    prepare,
)
from backend.app.services.retrieval.vector_search import RetrievedChunk


def _chunk(score=0.9, text="Annual leave is 18 days.", doc="leave.pdf"):
    return RetrievedChunk("c1", text, score, "d", doc, 3, "Leave", 1)


def test_build_context_numbers_and_truncates():
    chunks = [_chunk(text=f"Policy text {i} " + "x" * 2000) for i in range(10)]
    ctx, cites = build_context(chunks)
    assert len(ctx) <= MAX_CONTEXT_CHARS
    assert "[1]" in ctx and cites[0].document == "leave.pdf"
    assert cites[0].excerpt == chunks[0].text[:300]
    assert cites[0].page == 3 and cites[0].index == 1


def test_prompt_has_guardrails():
    from backend.app.services.generation.rag_pipeline import SYSTEM_PROMPT

    assert "ONLY" in SYSTEM_PROMPT and "[1]" in SYSTEM_PROMPT


def test_fallback_low_score_skips_llm():
    gen = MagicMock()
    res = answer_query("q", _search=lambda q, top_k=None, **_: [_chunk(score=0.1)], _generate=gen)
    assert res.fallback and "contact your HR team" in res.answer
    gen.assert_not_called()


def test_fallback_no_chunks():
    res = answer_query("q", _search=lambda q, top_k=None, **_: [], _generate=MagicMock())
    assert res.fallback


def test_answer_uses_citations_and_usage():
    gen = MagicMock(return_value=("Take 18 days [1].", {"prompt_tokens": 50, "completion_tokens": 5}))
    res = answer_query("How many leaves?", _search=lambda q, top_k=None, **_: [_chunk()], _generate=gen)
    assert not res.fallback and res.answer == "Take 18 days [1]."
    assert len(res.citations) == 1 and res.top_score == 0.9
    assert res.prompt_tokens == 50 and res.completion_tokens == 5


def test_parse_sse_line():
    line = 'data: {"choices": [{"delta": {"content": "hello"}}]}'
    assert parse_sse_line(line) == "hello"
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line(": keep-alive") is None
    assert parse_sse_line('data: {"choices": [{"delta": {}}]}') is None
    assert parse_sse_line("garbage") is None


def _api_client():
    import uuid

    user = User(email="e@c.com", password_hash="x", full_name="E", role=UserRole.employee)
    user.id = uuid.uuid4()
    user.is_active = True
    session = AsyncMock()
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


@pytest.fixture(autouse=True)
def _fake_cache():
    """Hermetic cache: memory L1 only (no real Redis/HF calls in endpoint tests)."""
    from backend.app.services.cache.semantic_cache import SemanticCache

    fake = SemanticCache(redis_fn=lambda: (_ for _ in ()).throw(Exception("no redis")),
                         embed_fn=lambda t: [1.0, 0.0])
    with patch("backend.app.api.v1.chat.get_cache", return_value=fake), \
         patch("backend.app.api.v1.chat._guard_injection",
               new=AsyncMock(return_value=None)):
        yield


def test_chat_endpoint_shape_and_logging():
    from backend.app.services.generation.rag_pipeline import RagAnswer

    client, session = _api_client()
    fake = RagAnswer(answer="18 days [1].", citations=[], fallback=False, top_score=0.9)
    with patch("backend.app.api.v1.chat.answer_query", return_value=fake):
        r = client.post("/api/v1/chat", json={"query": "leaves?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "18 days [1]." and body["fallback"] is False
    assert "latency_ms" in body and body["citations"] == []
    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_chat_stream_fallback_event():
    client, _ = _api_client()
    with patch("backend.app.api.v1.chat.prepare",
               return_value=([], [], [], SimpleNamespace(answer="contact HR"))):
        r = client.post("/api/v1/chat/stream", json={"query": "xyz"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "contact HR" in r.text and "[DONE]" in r.text


def test_chat_stream_tokens_and_citations():
    from backend.app.services.generation.rag_pipeline import Citation

    client, _ = _api_client()

    async def fake_stream(messages):
        yield "18 "
        yield "days."

    cites = [Citation(1, "leave.pdf", 3, None, "excerpt")]
    with patch("backend.app.api.v1.chat.prepare", return_value=([_chunk()], [], cites, None)), \
         patch("backend.app.api.v1.chat.generate_stream", return_value=fake_stream([])):
        r = client.post("/api/v1/chat/stream", json={"query": "leaves?"})
    assert r.status_code == 200
    assert "leave.pdf" in r.text and "18 " in r.text and "[DONE]" in r.text
