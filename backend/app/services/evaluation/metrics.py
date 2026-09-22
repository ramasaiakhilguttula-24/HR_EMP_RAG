"""In-house RAG metrics mirroring RAGAS definitions (Feature 17).

Why not the ragas package: ragas 0.4.3 fails at import with the installed
langchain-community 0.4.x (`No module named 'langchain_community.chat_models.vertexai'`,
verified 2026-09-21). These functions implement the same five scores with our
Groq judge + HF embeddings, and are injectable for offline tests.
"""
import re


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _yes_no(question: str, context: str, _generate) -> bool:
    text, _ = _generate([
        {"role": "system", "content": "Reply with exactly YES or NO."},
        {"role": "user", "content": f"{question}\n\nContext:\n{context}"},
    ])
    return text.strip().upper().startswith("YES")


def claim_supported(claim: str, contexts: list[str], _generate) -> bool:
    """A claim restating the user's own question counts as supported (conversational grounding)."""
    return _yes_no(f"Is this claim supported? Reply YES if it is stated in the context OR if it "
                   f"merely restates information from the user's question. Claim: {claim}",
                   "\n".join(contexts), _generate)


def _strip_markers(text: str) -> str:
    """Remove citation markers ([1], 【1】, [doc, page]) so they never become claims."""
    text = re.sub(r"【[^】]*】", "", text or "")
    text = re.sub(r"\[[^\]\n]{0,60}\]", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def faithfulness(answer: str, contexts: list[str], _generate) -> float:
    """Share of answer claims supported by retrieved contexts. Target > 0.85."""
    claims_text, _ = _generate([
        {"role": "system", "content": "Split the answer into atomic factual claims, one per line. No numbering."},
        {"role": "user", "content": _strip_markers(answer)},
    ])
    claims = [c for c in (claims_text or "").splitlines() if c.strip()]
    if not claims:
        return 0.0
    joined = "\n".join(contexts)
    supported = sum(1 for c in claims if claim_supported(c, joined, _generate))
    return supported / len(claims)


def answer_relevancy(question: str, answer: str, _generate, _embed) -> float:
    """Mean cosine between question and questions generated from the answer. Target > 0.80."""
    gen_text, _ = _generate([
        {"role": "system", "content": "Generate 3 distinct questions that this answer addresses, one per line."},
        {"role": "user", "content": answer},
    ])
    gen_qs = [q for q in gen_text.splitlines() if q.strip()][:3]
    if not gen_qs:
        return 0.0
    vecs = _embed([question] + gen_qs)
    return mean([cosine(vecs[0], v) for v in vecs[1:]])


def context_precision(question: str, contexts: list[str], _generate) -> float:
    """Rank-weighted share of retrieved contexts relevant to the question. Target > 0.75."""
    if not contexts:
        return 0.0
    rel = [1.0 if _yes_no(f"Is this excerpt relevant to the question: {question}?",
                          ctx, _generate) else 0.0 for ctx in contexts]
    if sum(rel) == 0:
        return 0.0
    weighted = sum((sum(rel[: k + 1]) / (k + 1)) * r for k, r in enumerate(rel))
    return weighted / sum(rel)


def context_recall(ground_truth: str, contexts: list[str], _generate) -> float:
    """Share of ground-truth sentences attributable to retrieved contexts. Target > 0.70."""
    sentences = split_sentences(ground_truth)
    if not sentences or not contexts:
        return 0.0
    joined = "\n".join(contexts)
    covered = sum(1 for s in sentences
                  if _yes_no(f"Can this statement be inferred? Statement: {s}", joined, _generate))
    return covered / len(sentences)


def answer_correctness(answer: str, ground_truth: str, _generate) -> float:
    """LLM judge 0..1 of answer vs reference. Target > 0.80."""
    text, _ = _generate([
        {"role": "system", "content": "Rate how well ANSWER matches REFERENCE as a number 0-100. Reply with only the number."},
        {"role": "user", "content": f"REFERENCE: {ground_truth}\nANSWER: {answer}"},
    ])
    m = re.search(r"\d+", text or "")
    return min(100, int(m.group())) / 100 if m else 0.0


METRICS = {
    "faithfulness": ("Faithfulness", 0.85),
    "answer_relevancy": ("Answer Relevancy", 0.80),
    "context_precision": ("Context Precision", 0.75),
    "context_recall": ("Context Recall", 0.70),
    "answer_correctness": ("Answer Correctness", 0.80),
}


def check_gates(scores: dict[str, float]) -> tuple[bool, list[str]]:
    """Returns (passed, failures). A metric fails when below its target."""
    failures = [f"{name} {scores.get(name, 0.0):.3f} < {METRICS[name][1]}"
                for name in METRICS if scores.get(name, 0.0) < METRICS[name][1]]
    return (not failures, failures)
