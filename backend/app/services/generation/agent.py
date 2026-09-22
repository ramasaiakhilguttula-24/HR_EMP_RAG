"""Agentic RAG: LangGraph ReAct loop over HR tools (Feature 15).

Reason → Act → Observe, max 5 iterations. Tools reuse the existing
retrieval/generation stack, so the agent inherits RBAC filters and citations.
"""
import json
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from backend.app.services.generation.rag_pipeline import generate as _groq_generate
from backend.app.core.tracing import traceable as _traceable

MAX_STEPS = 5

GRIEVANCE_HINTS = ("grievance", "harass", "posh complaint", "discriminat",
                   "retaliat", "unsafe workplace", "file a complaint")

TOOL_SPEC = """You are an HR assistant that reasons step by step. Reply with ONLY one JSON object.
Actions:
{"action": "search_policy", "args": {"query": "..."}}
{"action": "compare_documents", "args": {"doc_a": "...", "doc_b": "...", "aspect": "..."}}
{"action": "calculate_entitlement", "args": {"kind": "notice_period|annual_leave", "tenure_years": 3.5, "used_leaves": 0}}
{"action": "escalate_to_hr", "args": {"reason": "..."}}
{"action": "get_document_metadata", "args": {"document_name": "..."}}
Or finish: {"answer": "..."} (cite facts as [doc name, page]).
Rules: you MUST call search_policy at least once before answering (no exceptions —
never answer from pretraining); use search results before calculating; escalate
grievance/harassment topics immediately; never invent policy numbers."""


class AgentState(TypedDict, total=False):
    query: str
    steps: list[dict]
    pending: dict | None
    answer: str | None
    escalated: bool


def search_policy(args: dict, ctx: dict, _search=None) -> dict:
    from backend.app.services.retrieval.hybrid_search import hybrid_search

    search = _search or hybrid_search
    chunks = search(args.get("query", ""), top_k=5, user=ctx.get("user"))
    return {"chunks": [{"document": c.document_name, "page": c.page_number,
                        "text": c.text[:800], "score": round(c.score, 3)} for c in chunks]}


def compare_documents(args: dict, ctx: dict, _search=None, _generate=None) -> dict:
    from backend.app.services.generation.rag_pipeline import generate
    from backend.app.services.retrieval.hybrid_search import hybrid_search

    search = _search or hybrid_search
    gen = _generate or generate
    sides = {}
    for key in ("doc_a", "doc_b"):
        name = args.get(key, "")
        hits = search(f"{args.get('aspect', '')} {name}", top_k=3, user=ctx.get("user"))
        sides[key] = {"name": name,
                      "excerpts": [f"({h.document_name} p{h.page_number}) {h.text[:600]}" for h in hits]}
    text, _ = gen([
        {"role": "system", "content": "Compare two policy excerpts side by side, then state which is more employee-friendly and why. Cite sources."},
        {"role": "user", "content": f"Aspect: {args.get('aspect')}\nA: {sides['doc_a']}\nB: {sides['doc_b']}"},
    ])
    return {"comparison": text, "sources": [sides["doc_a"]["name"], sides["doc_b"]["name"]]}


NOTICE_RULE = "tenure < 2y → 30 days; ≥ 2y → 60 days (Separation Policy)"
LEAVE_RULE = "18 days annual leave per calendar year, all full-time staff (Leave Policy)"


def calculate_entitlement(args: dict, ctx: dict) -> dict:  # noqa: ARG001 - ctx kept for uniform tool signature
    """Deterministic calculator over stated demo policy rules (never LLM-guessed)."""
    kind = args.get("kind", "notice_period")
    tenure = float(args.get("tenure_years", 0))
    if kind == "annual_leave":
        used = float(args.get("used_leaves", 0))
        return {"result": f"{18 - used:.0f} days remaining", "rule": LEAVE_RULE,
                "inputs": {"tenure_years": tenure, "used_leaves": used}}
    days = 30 if tenure < 2 else 60
    return {"result": f"{days} days notice", "rule": NOTICE_RULE,
            "inputs": {"tenure_years": tenure}}


async def escalate_to_hr(args: dict, ctx: dict) -> dict:
    """Create a human-in-the-loop ticket. Returns ticket id."""
    from backend.app.models.escalation import Escalation

    db = ctx["db"]
    ticket = Escalation(user_id=getattr(ctx.get("user"), "id", None),
                        query=ctx.get("query", ""), reason=args.get("reason", "agent escalation"))
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return {"ticket_id": str(ticket.id), "status": "open"}


async def get_document_metadata(args: dict, ctx: dict) -> dict:
    from sqlalchemy import select

    from backend.app.models.document import Document

    name = args.get("document_name", "")
    rows = (await ctx["db"].execute(
        select(Document).where(Document.file_name.ilike(f"%{name}%")))).scalars().all()
    return {"documents": [{"file_name": d.file_name, "version": d.version,
                           "effective_date": str(d.effective_date) if d.effective_date else None,
                           "status": d.status.value,
                           "uploaded_by": str(d.uploaded_by) if d.uploaded_by else None}
                          for d in rows]}


TOOLS = {"search_policy": search_policy, "compare_documents": compare_documents,
         "calculate_entitlement": calculate_entitlement, "escalate_to_hr": escalate_to_hr,
         "get_document_metadata": get_document_metadata}


def _parse_action(text: str) -> dict | None:
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, AttributeError):
        return None
    return data if isinstance(data, dict) and ("action" in data or "answer" in data) else None


def _think_llm(query: str, steps: list[dict]) -> str:
    from backend.app.services.generation.rag_pipeline import generate

    history = "\n".join(f"Step {i+1} {s['tool']}: {json.dumps(s['observation'])[:1500]}"
                        for i, s in enumerate(steps))
    text, _ = generate([
        {"role": "system", "content": TOOL_SPEC},
        {"role": "user", "content": f"Question: {query}\n{history}\nNext JSON:"},
    ])
    return text


@_traceable(name="hr-agent", run_type="chain")
async def run_agent(query: str, user=None, db=None, top_k: int = 5,  # noqa: ARG001 - top_k reserved for per-tool budgets
                    _think=None, _generate=None, langsmith_extra: dict | None = None) -> dict:  # noqa: ARG001 - consumed by @traceable
    """Run the ReAct loop. Returns {answer, citations, steps, iterations, escalated}."""
    ctx = {"user": user, "db": db, "query": query}
    state: AgentState = {"query": query, "steps": [], "pending": None,
                         "answer": None, "escalated": False}

    async def think(s: AgentState) -> dict:
        if any(g in query.lower() for g in GRIEVANCE_HINTS) and not s["steps"]:
            return {"pending": {"action": "escalate_to_hr",
                                "args": {"reason": "grievance topic needs a human"}}}
        raw = _think(query, s["steps"]) if _think else _think_llm(query, s["steps"])
        if hasattr(raw, "__await__"):
            raw = await raw
        action = _parse_action(raw)
        if action is None:
            return {"pending": {"action": "__answer__", "args": {"text": raw}}}
        if "answer" in action:
            searched = any(s["tool"] == "search_policy" for s in s["steps"])
            if not searched:
                # Enforce search-first: models shortcut to direct answers otherwise.
                return {"pending": {"action": "search_policy", "args": {"query": query}}}
            return {"answer": str(action["answer"])}
        if action.get("action") not in TOOLS:
            return {"pending": {"action": "__answer__",
                                "args": {"text": f"I could not plan this query. {raw[:200]}"}}}
        return {"pending": {"action": action["action"], "args": action.get("args", {})}}

    async def act(s: AgentState) -> dict:
        pending = s["pending"] or {}
        if pending.get("action") == "__answer__":
            return {"answer": pending["args"].get("text", ""), "pending": None}
        tool = TOOLS[pending["action"]]
        obs = tool(pending["args"], ctx)
        if hasattr(obs, "__await__"):
            obs = await obs
        step = {"tool": pending["action"], "args": pending["args"], "observation": obs}
        escalated = s.get("escalated", False) or pending["action"] == "escalate_to_hr"
        return {"steps": s["steps"] + [step], "pending": None, "escalated": escalated}

    async def finalize(s: AgentState) -> dict:
        if s.get("answer"):
            return {}
        if not s["steps"]:
            return {"answer": "I could not find relevant HR information. Please contact HR directly."}
        gen = _generate or _groq_generate
        recap = "\n".join(f"- {st['tool']}: {json.dumps(st['observation'])[:1500]}" for st in s["steps"])
        text, _ = gen([
            {"role": "system", "content": "Answer the user's HR question using ONLY these tool observations. Cite sources."},
            {"role": "user", "content": f"Question: {query}\nObservations:\n{recap}"},
        ])
        return {"answer": text}

    def route(s: AgentState) -> str:
        if s.get("answer") is not None:
            return END
        if len(s["steps"]) >= MAX_STEPS:
            return "finalize"
        return "think"

    def route_think(s: AgentState) -> str:
        return END if s.get("answer") is not None else "act"

    graph = StateGraph(AgentState)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.add_node("finalize", finalize)
    graph.set_entry_point("think")
    graph.add_conditional_edges("think", route_think, {"act": "act", END: END})
    graph.add_conditional_edges("act", route, {"think": "think", "finalize": "finalize", END: END})
    graph.add_edge("finalize", END)
    out = await graph.compile().ainvoke(state)

    citations = []
    for st in out.get("steps", []):
        for c in (st["observation"].get("chunks") or []):
            citations.append({"document": c["document"], "page": c["page"],
                              "excerpt": c["text"][:300]})
    return {"answer": out.get("answer", ""), "citations": citations,
            "steps": out.get("steps", []), "iterations": len(out.get("steps", [])),
            "escalated": out.get("escalated", False)}


def describe_tools() -> list[dict[str, Any]]:
    return [{"name": n, "action": n} for n in TOOLS]
