"""RAG pipeline: retrieve -> prompt -> Groq generate -> cited answer.

No LangChain/LlamaIndex by design: direct Groq OpenAI-compatible calls over httpx
keep the learning path transparent (every byte of the prompt is visible here).
"""
import json
from dataclasses import dataclass, field

import httpx

from backend.app.core.config import get_settings
from backend.app.core.tracing import traceable

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_CONTEXT_CHARS = 6000
EXCERPT_CHARS = 300

SYSTEM_PROMPT = (
    "You are an HR policy assistant. Answer ONLY using the policy excerpts below.\n"
    "Rules:\n"
    "- If the excerpts do not contain the answer, say you do not know and advise contacting HR.\n"
    "- Never invent policy numbers, days, or procedures.\n"
    "- Cite every factual claim with the excerpt number, e.g. [1], [2].\n"
    "- Keep answers concise and employee-friendly."
)

FALLBACK_MSG = (
    "I couldn't find a confident answer in the HR policies "
    "(best match {score:.2f} is below our {threshold:.2f} threshold). "
    "Please contact your HR team directly."
)


@dataclass
class Citation:
    index: int
    document: str
    page: int | None
    section: str | None
    excerpt: str


@dataclass
class RagAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    fallback: bool = False
    top_score: float = 0.0
    chunks_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def build_context(chunks) -> tuple[str, list[Citation]]:
    """Number excerpts [1..n], truncate to MAX_CONTEXT_CHARS (top chunks first)."""
    blocks: list[str] = []
    citations: list[Citation] = []
    budget = MAX_CONTEXT_CHARS
    for i, c in enumerate(chunks, start=1):
        block = f"[{i}] ({c.document_name}, page {c.page_number}):\n{c.text}"
        if len(block) > budget and blocks:
            break
        blocks.append(block[:budget])
        budget -= len(blocks[-1])
        citations.append(
            Citation(index=i, document=c.document_name, page=c.page_number,
                     section=c.section_heading, excerpt=c.text[:EXCERPT_CHARS])
        )
    return "\n\n".join(blocks), citations


def _headers() -> dict:
    key = get_settings().GROQ_API_KEY
    if not key:
        raise ValueError("GROQ_API_KEY is missing. Add it to .env.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _payload(messages: list[dict], stream: bool) -> dict:
    s = get_settings()
    return {"model": s.LLM_MODEL, "messages": messages,
            "temperature": s.LLM_TEMP, "stream": stream}


@traceable(name="groq-generate", run_type="llm")
def generate(messages: list[dict]) -> tuple[str, dict]:
    """Blocking call. Returns (answer_text, usage_dict)."""
    with httpx.Client(timeout=60) as client:
        r = client.post(GROQ_URL, headers=_headers(), json=_payload(messages, False))
        r.raise_for_status()
        data = r.json()
    msg = data["choices"][0]["message"]["content"] or ""
    return msg.strip(), data.get("usage", {})


def parse_sse_line(line: str) -> str | None:
    """Extract token text from one SSE `data:` line. None = skip/end."""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data in ("[DONE]", ""):
        return None
    try:
        return json.loads(data)["choices"][0]["delta"].get("content") or None
    except (KeyError, ValueError, TypeError):
        return None


async def generate_stream(messages: list[dict]):
    """Async generator yielding answer tokens as they arrive."""
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", GROQ_URL, headers=_headers(),
                                 json=_payload(messages, True)) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                token = parse_sse_line(line)
                if token:
                    yield token


def prepare(query: str, top_k: int | None = None, _search=None, user=None,
            manual_filters: dict | None = None, use_profile_filters: bool = True,
            extract_filters: bool = False, search_mode: str = "dense",
            rerank: bool = False) -> tuple:
    """Retrieve + build prompt. Returns (chunks, messages, citations, fallback_answer)."""
    from backend.app.services.retrieval.hybrid_search import hybrid_search
    from backend.app.services.retrieval.reranker import rerank_chunks
    from backend.app.services.retrieval.vector_search import dense_search

    settings = get_settings()
    top_k = top_k or settings.TOP_K_RETRIEVE
    fetch = max(top_k, 20) if rerank else top_k
    search = _search or (hybrid_search if search_mode == "hybrid" else dense_search)
    chunks = search(query, top_k=fetch, user=user,
                    manual_filters=manual_filters, use_profile_filters=use_profile_filters,
                    extract_filters=extract_filters)
    if rerank and _search is None:
        ranked = rerank_chunks(query, chunks, top_n=top_k)
        # Graceful degradation: retrieval cleared the 0.5 bar, so never let the
        # reranker force a fallback by rejecting everything — keep the top chunk.
        chunks = ranked if ranked else chunks[:1]
    if not chunks:
        return [], [], [], RagAnswer(answer=FALLBACK_MSG.format(score=0.0, threshold=settings.SCORE_THRESHOLD),
                                     fallback=True)
    top = chunks[0].score
    if top < settings.SCORE_THRESHOLD:
        return chunks, [], [], RagAnswer(answer=FALLBACK_MSG.format(score=top, threshold=settings.SCORE_THRESHOLD),
                                         fallback=True, top_score=top, chunks_used=len(chunks))
    context, citations = build_context(chunks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Policy excerpts:\n{context}\n\nQuestion: {query}"},
    ]
    return chunks, messages, citations, None


@traceable(name="rag-answer", run_type="chain")
def answer_query(query: str, top_k: int | None = None, _search=None, _generate=None,
                 user=None, manual_filters: dict | None = None,
                 use_profile_filters: bool = True, extract_filters: bool = False,
                 search_mode: str = "dense", rerank: bool = False,
                 langsmith_extra: dict | None = None) -> RagAnswer:  # noqa: ARG001 - consumed by @traceable
    """Full pipeline (non-streaming). Injectable fakes for tests."""
    generate_fn = _generate or generate
    chunks, messages, citations, fallback = prepare(query, top_k, _search, user,
                                                    manual_filters, use_profile_filters,
                                                    extract_filters, search_mode, rerank)
    if fallback is not None:
        return fallback
    text, usage = generate_fn(messages)
    return RagAnswer(answer=text, citations=citations, fallback=False,
                     top_score=chunks[0].score if chunks else 0.0,
                     chunks_used=len(citations),
                     prompt_tokens=int(usage.get("prompt_tokens", 0)),
                     completion_tokens=int(usage.get("completion_tokens", 0)))
