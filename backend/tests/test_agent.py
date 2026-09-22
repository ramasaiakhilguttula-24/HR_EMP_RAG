"""Agentic RAG tests: tools, ReAct loop, cap, endpoint (faked LLM/search)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.main import app
from backend.app.models.user import User, UserRole
from backend.app.services.generation.agent import (
    MAX_STEPS,
    calculate_entitlement,
    compare_documents,
    escalate_to_hr,
    get_document_metadata,
    run_agent,
    search_policy,
)


def _ctx():
    return {"user": SimpleNamespace(id="u1"), "db": AsyncMock(), "query": "q"}


def test_calculate_notice():
    assert calculate_entitlement({"kind": "notice_period", "tenure_years": 3.5}, {})["result"] == "60 days notice"
    assert calculate_entitlement({"kind": "notice_period", "tenure_years": 1}, {})["result"] == "30 days notice"
    assert calculate_entitlement({"kind": "notice_period", "tenure_years": 2}, {})["result"] == "60 days notice"


def test_calculate_leave_balance():
    r = calculate_entitlement({"kind": "annual_leave", "tenure_years": 1, "used_leaves": 5}, {})
    assert r["result"] == "13 days remaining" and "18 days" in r["rule"]


def test_search_policy_shapes_chunks():
    chunk = SimpleNamespace(document_name="leave.pdf", page_number=2, text="x" * 900, score=0.9)
    out = search_policy({"query": "leave"}, {}, _search=lambda q, top_k=5, user=None: [chunk])
    assert out["chunks"][0]["document"] == "leave.pdf"
    assert len(out["chunks"][0]["text"]) == 800


def test_compare_documents_uses_both_sides():
    hit = SimpleNamespace(document_name="d.pdf", page_number=1, text="t", score=0.9)
    calls = []

    def fake_search(q, top_k=3, user=None):
        calls.append(q)
        return [hit]

    out = compare_documents({"doc_a": "India", "doc_b": "UK", "aspect": "maternity"},
                            {}, _search=fake_search,
                            _generate=lambda msgs: ("A beats B.", {}))
    assert out["comparison"] == "A beats B."
    assert len(calls) == 2 and out["sources"] == ["India", "UK"]


def test_escalate_creates_ticket():
    import asyncio

    db = AsyncMock()
    db.add = MagicMock()
    ticket = SimpleNamespace(id="t-1")
    db.refresh.side_effect = lambda o: setattr(o, "id", "t-1") or None
    out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        escalate_to_hr({"reason": "harassment"}, {"user": SimpleNamespace(id="u1"),
                                                  "db": db, "query": "help"}))
    assert out["ticket_id"] == "t-1" and out["status"] == "open"
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_metadata_shapes_rows():
    import asyncio

    row = SimpleNamespace(file_name="leave.pdf", version=2, effective_date=None,
                          status=SimpleNamespace(value="ready"), uploaded_by=None)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))
    out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        get_document_metadata({"document_name": "leave"}, {"db": db}))
    assert out["documents"][0]["version"] == 2


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_react_loop_with_fake_search(monkeypatch):
    import backend.app.services.generation.agent as ag

    chunk = SimpleNamespace(document_name="sep.pdf", page_number=5, text="60 days", score=0.9)
    monkeypatch.setitem(ag.TOOLS, "search_policy",
                        lambda args, ctx, _search=None: {"chunks": [{"document": "sep.pdf", "page": 5, "text": "60 days", "score": 0.9}]})
    script = [
        '{"action": "search_policy", "args": {"query": "notice"}}',
        '{"action": "calculate_entitlement", "args": {"kind": "notice_period", "tenure_years": 3.5}}',
        '{"answer": "Serve 60 days."}',
    ]
    res = _run(run_agent("notice?", _think=lambda q, steps: script[min(len(steps), 2)]))
    assert res["iterations"] == 2
    assert [s["tool"] for s in res["steps"]] == ["search_policy", "calculate_entitlement"]
    assert res["answer"] == "Serve 60 days."
    assert res["citations"][0]["document"] == "sep.pdf"


def test_max_steps_cap():
    import backend.app.services.generation.agent as ag

    monkeypatch_calls = {"n": 0}

    def always_act(q, steps):
        return '{"action": "search_policy", "args": {"query": "x"}}'

    chunk = {"document": "d.pdf", "page": 1, "text": "t", "score": 0.9}
    import unittest.mock as mock

    with mock.patch.dict(ag.TOOLS, {"search_policy": lambda args, ctx, _search=None: {"chunks": [chunk]}}):
        res = _run(run_agent("loop?", _think=always_act,
                             _generate=lambda msgs: ("final synthesis", {})))
    assert res["iterations"] == MAX_STEPS
    assert res["answer"] == "final synthesis"


def test_grievance_auto_escalates():
    import asyncio
    import unittest.mock as mock

    import backend.app.services.generation.agent as ag

    db = AsyncMock()
    db.add = MagicMock()
    db.refresh.side_effect = lambda o: setattr(o, "id", "t-9") or None
    res = _run(run_agent("I want to file a harassment grievance", user=SimpleNamespace(id="u1"), db=db,
                         _think=lambda q, steps: '{"answer": "done"}' if steps else (_ for _ in ()).throw(AssertionError("should escalate first"))))
    assert res["escalated"] is True
    assert res["steps"][0]["tool"] == "escalate_to_hr"


def test_search_first_enforced(monkeypatch):
    import backend.app.services.generation.agent as ag

    monkeypatch.setitem(ag.TOOLS, "search_policy",
                        lambda args, ctx, _search=None: {"chunks": []})
    res = _run(run_agent("notice period?", user=None, db=None,
                         _think=lambda q, steps: '{"answer": "60 days."}'))
    assert res["steps"] and res["steps"][0]["tool"] == "search_policy"
    assert res["answer"] == "60 days."


def test_agent_endpoint():
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
    fake = {"answer": "60 days.", "citations": [], "steps": [], "iterations": 0, "escalated": False}
    with patch("backend.app.api.v1.agent.run_agent", new=AsyncMock(return_value=fake)), \
         patch("backend.app.api.v1.agent._guard_injection", new=AsyncMock(return_value=None)), \
         patch("backend.app.api.v1.agent._mask_query", new=AsyncMock(side_effect=lambda q, u, d: q)):
        r = TestClient(app).post("/api/v1/agent/chat", json={"query": "notice?"})
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "60 days." and r.json()["iterations"] == 0
