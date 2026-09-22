"""Dense vector search against Qdrant `hr_policies` (cosine, HNSW).

Phase 2 adds hybrid + rerank on top; this module stays the dense base.
Feature 8: metadata filtering (profile auto-filter + manual override + LLM extraction).
RBAC access_level filtering lands in Phase 3 — currently only is_active=true.
"""
from dataclasses import dataclass

from backend.app.core.config import get_settings
from backend.app.core.tracing import traceable
from backend.app.services.retrieval.filters import build_qdrant_filter, extract_filters_llm


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    document_id: str
    document_name: str
    page_number: int | None
    section_heading: str | None
    version: int | None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def mmr_select(
    query_vec: list[float],
    cand_vecs: list[list[float]],
    scores: list[float],
    top_k: int,
    lambda_: float = 0.7,
) -> list[int]:
    """Maximal Marginal Relevance: relevance vs diversity. Returns selected indices."""
    n = len(cand_vecs)
    top_k = min(top_k, n)
    if top_k >= n:
        return list(range(n))
    selected = [max(range(n), key=lambda i: scores[i])]
    while len(selected) < top_k:
        best, best_val = -1, float("-inf")
        for i in range(n):
            if i in selected:
                continue
            diversity_penalty = max(_cosine(cand_vecs[i], cand_vecs[j]) for j in selected)
            val = lambda_ * scores[i] - (1 - lambda_) * diversity_penalty
            if val > best_val:
                best, best_val = i, val
        selected.append(best)
    return selected


@traceable(name="dense-search", run_type="retriever")
def dense_search(
    query: str,
    top_k: int | None = None,
    mmr_lambda: float = 0.7,
    user=None,
    manual_filters: dict | None = None,
    use_profile_filters: bool = True,
    extract_filters: bool = False,
    qdrant_client=None,
    embedder=None,
) -> list[RetrievedChunk]:
    """Embed query with the ingestion model, fetch candidates, MMR-diversify."""
    from backend.app.core.qdrant import get_qdrant_client
    from backend.app.services.ingestion.embedder import get_embedder

    settings = get_settings()
    top_k = top_k or settings.TOP_K_RETRIEVE
    client = qdrant_client or get_qdrant_client()
    embedder = embedder or get_embedder()

    merged_manual = dict(manual_filters or {})
    if extract_filters:
        merged_manual = {**extract_filters_llm(query), **merged_manual}
    qdrant_filter, _ = build_qdrant_filter(user, merged_manual, use_profile_filters)

    query_vec = embedder.embed_query(query)
    over_fetch = max(top_k * 3, top_k)
    hits = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=query_vec,
        using="dense",
        limit=over_fetch,
        query_filter=qdrant_filter,
        with_payload=True,
        with_vectors=True,
    ).points

    if not hits:
        return []
    vecs = [list(h.vector) if isinstance(h.vector, list) else list(h.vector["dense"]) for h in hits]
    scores = [float(h.score) for h in hits]
    picked = mmr_select(query_vec, vecs, scores, top_k, mmr_lambda)

    chunks: list[RetrievedChunk] = []
    for i in picked:
        h = hits[i]
        p = h.payload or {}
        chunks.append(
            RetrievedChunk(
                chunk_id=str(p.get("chunk_id", h.id)),
                text=str(p.get("text", "")),
                score=scores[i],
                document_id=str(p.get("document_id", "")),
                document_name=str(p.get("document_name", "")),
                page_number=p.get("page_number"),
                section_heading=p.get("section_heading"),
                version=p.get("version"),
            )
        )
    return chunks
