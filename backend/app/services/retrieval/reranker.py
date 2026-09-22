"""Cohere Rerank API (Feature 10). Cross-encoder scores for final ordering."""
from dataclasses import replace

import httpx

from backend.app.core.tracing import traceable

COHERE_URL = "https://api.cohere.com/v2/rerank"


@traceable(name="cohere-rerank", run_type="retriever")
def cohere_rerank(query: str, texts: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
    """Returns [(original_index, relevance_score)] ordered by relevance."""
    from backend.app.core.config import get_settings

    settings = get_settings()
    if not settings.COHERE_API_KEY:
        raise ValueError("COHERE_API_KEY is missing. Add it to .env.")
    if not texts:
        return []
    with httpx.Client(timeout=30) as client:
        r = client.post(
            COHERE_URL,
            headers={"Authorization": f"Bearer {settings.COHERE_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": settings.RERANK_MODEL, "query": query,
                  "documents": texts, "top_n": top_n or len(texts)},
        )
        r.raise_for_status()
        results = r.json()["results"]
    return [(int(x["index"]), float(x["relevance_score"])) for x in results]


def rerank_chunks(query: str, chunks: list, top_n: int | None = None,
                  threshold: float | None = None, _rerank=None) -> list:
    """Reorder chunks by cross-encoder relevance, drop score < threshold."""
    from backend.app.core.config import get_settings as _gs

    settings = _gs()
    top_n = top_n or settings.RERANK_TOP_N
    threshold = settings.RERANK_THRESHOLD if threshold is None else threshold
    if not chunks:
        return []
    rerank_fn = _rerank or cohere_rerank
    ranked = rerank_fn(query, [c.text for c in chunks], top_n=min(top_n, len(chunks)))
    out = []
    for idx, score in ranked:
        if score < threshold or len(out) >= top_n:
            continue
        out.append(replace(chunks[idx], score=score))
    return out
