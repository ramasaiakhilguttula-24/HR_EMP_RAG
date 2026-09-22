"""Hybrid fusion + RRF/weighted math (faked Qdrant)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.app.services.retrieval.hybrid_search import _normalize, hybrid_search


def _hit(i, score, vec=None):
    return SimpleNamespace(
        id=f"h{i}", score=score, vector=vec,
        payload={"chunk_id": f"c{i}", "text": f"t{i}", "document_id": "d",
                 "document_name": "doc.pdf", "page_number": 1,
                 "section_heading": None, "version": 1},
    )


def _client_rrf():
    c = MagicMock()
    c.query_points.return_value = SimpleNamespace(points=[_hit(0, 0.06), _hit(1, 0.03)])
    return c


def test_rrf_fusion_normalizes_scores():
    fake_dense = MagicMock()
    fake_dense.embed_query.return_value = [1.0] * 4
    fake_sparse = MagicMock()
    fake_sparse.embed_query.return_value = {"indices": [1], "values": [0.5]}
    chunks = hybrid_search("posh article", top_k=2, qdrant_client=_client_rrf(),
                           embedder=fake_dense, sparse_embedder=fake_sparse)
    assert len(chunks) == 2
    assert chunks[0].score == 1.0 and chunks[1].score == 0.0  # min-max normalized
    assert fake_sparse.embed_query.called


def test_rrf_prefetch_uses_bm25():
    c = _client_rrf()
    fake_dense = MagicMock()
    fake_dense.embed_query.return_value = [1.0]
    fake_sparse = MagicMock()
    fake_sparse.embed_query.return_value = {"indices": [2], "values": [1.0]}
    hybrid_search("q", top_k=1, qdrant_client=c, embedder=fake_dense,
                  sparse_embedder=fake_sparse)
    _, kwargs = c.query_points.call_args
    assert len(kwargs["prefetch"]) == 2
    assert kwargs["prefetch"][1].using == "bm25"


def _client_weighted(dense_scores, sparse_scores):
    c = MagicMock()
    c.query_points.side_effect = [
        SimpleNamespace(points=[_hit(i, s) for i, s in enumerate(dense_scores)]),
        SimpleNamespace(points=[_hit(i, s) for i, s in enumerate(sparse_scores)]),
    ]
    return c


def test_weighted_alpha_1_is_dense_order():
    fake = MagicMock()
    fake.embed_query.return_value = [1.0]
    fake_sp = MagicMock()
    fake_sp.embed_query.return_value = {"indices": [1], "values": [1.0]}
    chunks = hybrid_search("q", top_k=2, fusion="weighted", alpha=1.0,
                           qdrant_client=_client_weighted([0.9, 0.1], [0.1, 0.9]),
                           embedder=fake, sparse_embedder=fake_sp)
    assert [c.chunk_id for c in chunks] == ["c0", "c1"]


def test_weighted_alpha_0_is_sparse_order():
    fake = MagicMock()
    fake.embed_query.return_value = [1.0]
    fake_sp = MagicMock()
    fake_sp.embed_query.return_value = {"indices": [1], "values": [1.0]}
    chunks = hybrid_search("q", top_k=2, fusion="weighted", alpha=0.0,
                           qdrant_client=_client_weighted([0.9, 0.1], [0.1, 0.9]),
                           embedder=fake, sparse_embedder=fake_sp)
    assert [c.chunk_id for c in chunks] == ["c1", "c0"]


def test_normalize_flat_scores():
    assert _normalize([0.5, 0.5]) == [1.0, 1.0]


def test_hybrid_empty():
    c = MagicMock()
    c.query_points.return_value = SimpleNamespace(points=[])
    fake = MagicMock()
    fake.embed_query.return_value = [1.0]
    fake_sp = MagicMock()
    fake_sp.embed_query.return_value = {"indices": [], "values": []}
    assert hybrid_search("q", qdrant_client=c, embedder=fake, sparse_embedder=fake_sp) == []
