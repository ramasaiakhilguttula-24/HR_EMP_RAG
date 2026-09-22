"""Hybrid dense + BM25 sparse search with RRF / weighted fusion (Feature 9).

Fusion scores are min-max normalized to [0,1] so downstream thresholds
(e.g. the 0.5 RAG fallback) keep working across fusion modes.
"""
from qdrant_client.http.models import FusionQuery, Fusion, Prefetch, SparseVector

from backend.app.core.config import get_settings
from backend.app.core.tracing import traceable
from backend.app.services.retrieval.filters import build_qdrant_filter
from backend.app.services.retrieval.vector_search import RetrievedChunk


def _normalize(scores: list[float]) -> list[float]:
    lo, hi = min(scores), max(scores)
    if hi <= lo:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def _to_chunks(hits, scores: list[float]) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for h, score in zip(hits, scores):
        p = h.payload or {}
        chunks.append(
            RetrievedChunk(
                chunk_id=str(p.get("chunk_id", h.id)),
                text=str(p.get("text", "")),
                score=float(score),
                document_id=str(p.get("document_id", "")),
                document_name=str(p.get("document_name", "")),
                page_number=p.get("page_number"),
                section_heading=p.get("section_heading"),
                version=p.get("version"),
            )
        )
    return chunks


@traceable(name="hybrid-search", run_type="retriever")
def hybrid_search(
    query: str,
    top_k: int | None = None,
    fusion: str = "rrf",
    alpha: float = 0.7,
    user=None,
    manual_filters: dict | None = None,
    use_profile_filters: bool = True,
    extract_filters: bool = False,
    qdrant_client=None,
    embedder=None,
    sparse_embedder=None,
) -> list[RetrievedChunk]:
    """RRF (rank-only) or weighted (alpha blend of min-max scores) fusion."""
    from backend.app.core.qdrant import get_qdrant_client
    from backend.app.services.ingestion.embedder import BM25Embedder, get_embedder

    settings = get_settings()
    top_k = top_k or settings.TOP_K_RETRIEVE
    fetch = max(top_k * 3, top_k)
    client = qdrant_client or get_qdrant_client()
    embedder = embedder or get_embedder()
    sparse_embedder = sparse_embedder or BM25Embedder()

    merged_manual = dict(manual_filters or {})
    if extract_filters:
        from backend.app.services.retrieval.filters import extract_filters_llm

        merged_manual = {**extract_filters_llm(query), **merged_manual}
    qdrant_filter, _ = build_qdrant_filter(user, merged_manual, use_profile_filters)

    dense_vec = embedder.embed_query(query)
    sp = sparse_embedder.embed_query(query)
    sparse_vec = SparseVector(indices=sp["indices"], values=sp["values"])

    if fusion == "weighted":
        return _weighted(client, settings, dense_vec, sparse_vec, qdrant_filter,
                         top_k, fetch, alpha)

    hits = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        prefetch=[
            Prefetch(query=dense_vec, using="dense", limit=fetch, filter=qdrant_filter),
            Prefetch(query=sparse_vec, using="bm25", limit=fetch, filter=qdrant_filter),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        query_filter=qdrant_filter,
        limit=fetch,
        with_payload=True,
    ).points
    return _to_chunks(hits[:top_k], _normalize([float(h.score) for h in hits[:top_k]])) if hits else []


def _weighted(client, settings, dense_vec, sparse_vec, qdrant_filter,
              top_k: int, fetch: int, alpha: float) -> list[RetrievedChunk]:
    """alpha * dense_norm + (1-alpha) * sparse_norm, merged by point id."""
    dense_hits = client.query_points(
        collection_name=settings.QDRANT_COLLECTION, query=dense_vec, using="dense",
        limit=fetch, query_filter=qdrant_filter, with_payload=True).points
    sparse_hits = client.query_points(
        collection_name=settings.QDRANT_COLLECTION, query=sparse_vec, using="bm25",
        limit=fetch, query_filter=qdrant_filter, with_payload=True).points

    d_scores = _normalize([float(h.score) for h in dense_hits]) if dense_hits else []
    s_scores = _normalize([float(h.score) for h in sparse_hits]) if sparse_hits else []
    merged: dict = {}
    for h, s in zip(dense_hits, d_scores):
        merged[str(h.id)] = [h, alpha * s]
    for h, s in zip(sparse_hits, s_scores):
        if str(h.id) in merged:
            merged[str(h.id)][1] += (1 - alpha) * s
        else:
            merged[str(h.id)] = [h, (1 - alpha) * s]
    ranked = sorted(merged.values(), key=lambda t: t[1], reverse=True)[:top_k]
    return _to_chunks([h for h, _ in ranked], [s for _, s in ranked])
