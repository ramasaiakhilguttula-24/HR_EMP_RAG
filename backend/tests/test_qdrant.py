"""Qdrant collection + payload index tests (mocked client)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.core.qdrant import PAYLOAD_INDEXES, ensure_collection


def _client(exists=True, schema=None):
    c = MagicMock()
    c.collection_exists.return_value = exists
    c.get_collection.return_value = SimpleNamespace(payload_schema=schema or {})
    return c


def test_creates_collection_and_all_indexes_when_missing():
    c = _client(exists=False)
    assert ensure_collection(c) == "hr_policies"
    c.create_collection.assert_called_once()
    indexed = {call.args[1] for call in c.create_payload_index.call_args_list}
    assert indexed == set(PAYLOAD_INDEXES.keys())


def test_skips_existing_indexes():
    c = _client(exists=True, schema={"is_active": object(), "department": object()})
    ensure_collection(c)
    c.create_collection.assert_not_called()
    indexed = {call.args[1] for call in c.create_payload_index.call_args_list}
    assert "is_active" not in indexed and "department" not in indexed
    assert "location" in indexed


def test_index_race_never_fails():
    c = _client(exists=True)
    c.create_payload_index.side_effect = Exception("already exists")
    assert ensure_collection(c) == "hr_policies"


def test_lifespan_runs_setup_and_survives_failure(monkeypatch):
    import asyncio

    from backend.app.main import lifespan

    calls = {"n": 0}

    async def fake_to_thread(fn, *a, **k):
        calls["n"] += 1
        return fn()

    async def boom(fn, *a, **k):
        raise RuntimeError("qdrant down")

    async def run():
        async with lifespan(MagicMock()):
            pass

    monkeypatch.setattr("backend.app.main.asyncio", SimpleNamespace(to_thread=fake_to_thread))
    with patch("backend.app.core.qdrant.ensure_collection", return_value="hr_policies"):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(run())
    assert calls["n"] == 1

    monkeypatch.setattr("backend.app.main.asyncio", SimpleNamespace(to_thread=boom))
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(run())  # must not raise
