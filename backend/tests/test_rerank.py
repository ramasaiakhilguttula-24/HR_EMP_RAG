"""Cohere rerank parsing + threshold/top_n behavior (mocked HTTP)."""
from unittest.mock import MagicMock, patch

from backend.app.services.retrieval.reranker import cohere_rerank, rerank_chunks
from backend.app.services.retrieval.vector_search import RetrievedChunk


def _chunk(i, score=0.9):
    return RetrievedChunk(f"c{i}", f"text {i}", score, "d", "doc.pdf", 1, None, 1)


def _cohere_client(results):
    resp = MagicMock()
    resp.json.return_value = {"results": results}
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = resp
    return client


def test_cohere_rerank_parses():
    client = _cohere_client([{"index": 1, "relevance_score": 0.8},
                             {"index": 0, "relevance_score": 0.2}])
    with patch("httpx.Client", return_value=client):
        out = cohere_rerank("q", ["a", "b"], top_n=2)
    assert out == [(1, 0.8), (0, 0.2)]
    _, kwargs = client.post.call_args
    assert "v2/rerank" in "https://api.cohere.com/v2/rerank"
    assert kwargs["json"]["top_n"] == 2


def test_cohere_rerank_requires_key(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.get_settings",
                        lambda: type("S", (), {"COHERE_API_KEY": "", "RERANK_MODEL": "m"})())
    import pytest

    with pytest.raises(ValueError, match="COHERE_API_KEY"):
        cohere_rerank("q", ["a"])


def test_rerank_chunks_reorders_and_replaces_scores():
    fake = lambda q, texts, top_n=None: [(2, 0.95), (0, 0.5), (1, 0.4)]
    out = rerank_chunks("q", [_chunk(0), _chunk(1), _chunk(2)], top_n=3, _rerank=fake)
    assert [c.chunk_id for c in out] == ["c2", "c0", "c1"]
    assert out[0].score == 0.95


def test_rerank_chunks_drops_below_threshold():
    fake = lambda q, texts, top_n=None: [(0, 0.9), (1, 0.1)]
    out = rerank_chunks("q", [_chunk(0), _chunk(1)], top_n=2, threshold=0.3, _rerank=fake)
    assert [c.chunk_id for c in out] == ["c0"]


def test_rerank_chunks_caps_top_n():
    fake = lambda q, texts, top_n=None: [(i, 0.9 - i * 0.01) for i in range(5)]
    out = rerank_chunks("q", [_chunk(i) for i in range(5)], top_n=2, threshold=0.0, _rerank=fake)
    assert len(out) == 2


def test_rerank_chunks_empty():
    assert rerank_chunks("q", [], _rerank=MagicMock()) == []
