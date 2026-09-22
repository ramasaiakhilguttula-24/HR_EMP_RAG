"""Chat + retrieve routes. Phase 1: /retrieve (F5) + /chat + /chat/stream (F6)."""
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.query_log import QueryLog, SecurityEvent, SecurityEventType
from backend.app.models.user import User
from backend.app.schemas.chat import ChatIn, ChatOut, CitationOut
from backend.app.schemas.retrieval import ChunkOut, RetrieveIn, RetrieveOut
from backend.app.services.cache.semantic_cache import get_cache
from backend.app.services.generation.rag_pipeline import answer_query, generate_stream, prepare
from backend.app.services.retrieval.hybrid_search import hybrid_search
from backend.app.services.retrieval.reranker import rerank_chunks
from backend.app.services.retrieval.vector_search import dense_search

router = APIRouter(tags=["chat"])


async def _mask_query(query: str, user: User, db: AsyncSession) -> str:
    """F13: mask PII in user input, audit when found. Returns masked query."""
    from backend.app.services.security.pii_masker import mask_text

    masked, findings = mask_text(query)
    if findings:
        db.add(SecurityEvent(user_id=user.id, event_type=SecurityEventType.pii_detected,
                             details={"stage": "query", "count": len(findings),
                                      "entities": sorted({f["entity"] for f in findings})}))
        await db.commit()
    return masked


async def _mask_output(answer: str, user: User, db: AsyncSession) -> str:
    """F13: mask PII accidentally present in LLM output (/chat only; streams mask input)."""
    from backend.app.services.security.pii_masker import mask_text

    masked, findings = mask_text(answer)
    if findings:
        db.add(SecurityEvent(user_id=user.id, event_type=SecurityEventType.pii_detected,
                             details={"stage": "output", "count": len(findings),
                                      "entities": sorted({f["entity"] for f in findings})}))
        await db.commit()
    return masked


async def _guard_injection(query: str, user: User, db: AsyncSession) -> None:
    """F12: block prompt injection before any retrieval/generation. Raises 403."""
    from backend.app.core.token_blacklist import is_injection_locked, record_injection
    from backend.app.services.security.injection_detector import detect

    identifier = str(user.id)
    if await is_injection_locked(identifier):
        raise HTTPException(status_code=403,
                            detail="Account temporarily locked after repeated injection attempts.")
    is_attack, layer = detect(query)
    if is_attack:
        count = await record_injection(identifier)
        db.add(SecurityEvent(user_id=user.id, event_type=SecurityEventType.injection_attempt,
                             details={"layer": layer, "query": query[:200], "strike": count}))
        await db.commit()
        # Webhook alert to security team: stubbed (no URL configured).
        raise HTTPException(status_code=403,
                            detail="Request blocked: prompt injection detected.")


@router.post("/retrieve", response_model=RetrieveOut)
async def retrieve(
    body: RetrieveIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    await _guard_injection(body.query, user, db)
    query = await _mask_query(body.query, user, db)
    fetch = max(body.top_k, 20) if body.rerank else body.top_k
    common = dict(user=user, manual_filters=body.filters,
                  use_profile_filters=body.use_profile_filters,
                  extract_filters=body.extract_filters)
    if body.search_mode == "hybrid":
        chunks = hybrid_search(query, top_k=fetch, **common)
    else:
        lambda_ = 1.0 if not body.use_mmr else 0.7
        chunks = dense_search(query, top_k=fetch, mmr_lambda=lambda_, **common)
    if body.rerank:
        ranked = rerank_chunks(query, chunks, top_n=body.top_k)
        chunks = ranked if ranked else chunks[:1]
    else:
        chunks = chunks[: body.top_k]
    latency_ms = int((time.perf_counter() - started) * 1000)

    # Feedback loop: log query + results for later evaluation (Feature 17).
    db.add(
        QueryLog(
            user_id=user.id,
            query=body.query,
            normalized_query=body.query.strip().lower(),
            filters=body.filters,
            retrieved_chunk_ids=[c.chunk_id for c in chunks],
            retrieval_scores=[c.score for c in chunks],
            latency_ms=latency_ms,
            cache_hit=False,
        )
    )
    await db.commit()

    return RetrieveOut(
        query=body.query,
        chunks=[
            ChunkOut(
                chunk_id=c.chunk_id, text=c.text, score=c.score,
                document_name=c.document_name, page_number=c.page_number,
                section_heading=c.section_heading,
            )
            for c in chunks
        ],
        latency_ms=latency_ms,
    )


def _to_citation_out(c) -> CitationOut:
    return CitationOut(index=c.index, document=c.document, page=c.page,
                       section=c.section, excerpt=c.excerpt)


class FeedbackIn(BaseModel):
    query_log_id: str
    score: int = Field(ge=-1, le=1)
    run_id: str | None = None


@router.post("/feedback")
async def feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Thumbs up/down: stored in Postgres, attached to LangSmith run when known."""
    from backend.app.core.tracing import log_feedback

    try:
        log_id = uuid.UUID(body.query_log_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid log id")
    row = (await db.execute(select(QueryLog).where(QueryLog.id == log_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found")
    row.feedback = body.score
    await db.commit()
    attached = log_feedback(body.run_id or "", body.score) if body.run_id else False
    return {"status": "recorded", "langsmith_attached": attached}


@router.post("/chat", response_model=ChatOut)
async def chat(
    body: ChatIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    await _guard_injection(body.query, user, db)
    query = await _mask_query(body.query, user, db)
    params = {"top_k": body.top_k, "filters": body.filters,
              "profile": body.use_profile_filters, "extract": body.extract_filters,
              "mode": body.search_mode, "rerank": body.rerank}
    cache = get_cache()
    cached = await cache.get(query, params)
    if cached is not None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        cites = [CitationOut(**c) for c in cached["citations"]]
        db.add(QueryLog(user_id=user.id, query=query,
                        normalized_query=query.strip().lower(),
                        filters=body.filters, answer=cached["answer"],
                        citations=cached["citations"], latency_ms=latency_ms,
                        cache_hit=True))
        await db.commit()
        return ChatOut(answer=cached["answer"], citations=cites, fallback=False,
                       latency_ms=latency_ms, cached=True)

    res = answer_query(query, top_k=body.top_k, user=user,
                       manual_filters=body.filters,
                       use_profile_filters=body.use_profile_filters,
                       extract_filters=body.extract_filters,
                       search_mode=body.search_mode, rerank=body.rerank,
                       langsmith_extra={"metadata": {"user_id": str(user.id),
                                                     "role": user.role.value,
                                                     "endpoint": "chat"}})
    latency_ms = int((time.perf_counter() - started) * 1000)
    answer = await _mask_output(res.answer, user, db)

    db.add(
        QueryLog(
            user_id=user.id,
            query=query,
            normalized_query=query.strip().lower(),
            filters=body.filters,
            retrieved_chunk_ids=[],  # chunk ids available via /retrieve logs; answer logged here
            answer=answer,
            citations=[c.__dict__ for c in res.citations],
            latency_ms=latency_ms,
            tokens_in=res.prompt_tokens,
            tokens_out=res.completion_tokens,
            cache_hit=False,
        )
    )
    await db.commit()

    if not res.fallback:
        await cache.put(query, params,
                        {"answer": answer,
                         "citations": [c.__dict__ for c in res.citations]},
                        category=(body.filters or {}).get("policy_category"))

    return ChatOut(answer=answer, citations=[_to_citation_out(c) for c in res.citations],
                   fallback=res.fallback, latency_ms=latency_ms)


@router.post("/chat/stream")
async def chat_stream(
    body: ChatIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _guard_injection(body.query, user, db)
    query = await _mask_query(body.query, user, db)
    params = {"top_k": body.top_k, "filters": body.filters,
              "profile": body.use_profile_filters, "extract": body.extract_filters,
              "mode": body.search_mode, "rerank": body.rerank}
    cache = get_cache()
    cached = await cache.get(query, params)
    if cached is not None:
        cites = [CitationOut(**c) for c in cached["citations"]]
        words = cached["answer"].split(" ")

        async def _cached_gen():
            yield f"data: {json.dumps({'citations': cached['citations']})}\n\n"
            for i in range(0, len(words), 10):
                yield f"data: {json.dumps({'token': ' '.join(words[i:i + 10]) + ' '})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_cached_gen(), media_type="text/event-stream")

    chunks, messages, citations, fallback = prepare(query, top_k=body.top_k, user=user,
                                                      manual_filters=body.filters,
                                                      use_profile_filters=body.use_profile_filters,
                                                      extract_filters=body.extract_filters,
                                                      search_mode=body.search_mode,
                                                      rerank=body.rerank)

    async def gen():
        if fallback is not None:
            yield f"data: {json.dumps({'answer': fallback.answer, 'fallback': True})}\n\n"
        else:
            yield f"data: {json.dumps({'citations': [c.__dict__ for c in citations]})}\n\n"
            async for token in generate_stream(messages):
                yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
