"""Filter builder + LLM extraction tests (Feature 8)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.services.retrieval.filters import (
    build_qdrant_filter,
    extract_filters_llm,
    profile_of,
)


def _user(**kw):
    role = SimpleNamespace(value=kw.pop("role", "employee"))
    attrs = {"department": None, "location": None, "employment_type": None, "seniority": None}
    attrs.update(kw)
    return SimpleNamespace(role=role, **attrs)


def _keys(f):
    return sorted(c.key for c in f.must)


def test_profile_auto_filter():
    u = _user(department="Engineering", location="India")
    f, applied = build_qdrant_filter(u, None, True)
    assert applied == {"department": "Engineering", "location": "India"}
    assert _keys(f) == ["access_level", "department", "is_active", "location"]


def test_manual_overrides_profile():
    u = _user(location="India")
    f, applied = build_qdrant_filter(u, {"location": "UK"}, True)
    assert applied["location"] == "UK"
    loc = [c for c in f.must if c.key == "location"]
    assert loc[0].match.value == "UK"


def test_employee_cannot_disable_profile_filter():
    u = _user(role="employee", location="India")
    f, applied = build_qdrant_filter(u, None, False)
    assert applied.get("location") == "India"  # forced on for non-privileged


def test_admin_can_disable_profile_filter():
    u = _user(role="admin", location="India")
    f, applied = build_qdrant_filter(u, None, False)
    assert "location" not in applied and _keys(f) == ["is_active"]


def test_effective_date_range():
    f, applied = build_qdrant_filter(None, {"effective_date_from": "2024-01-01"}, False)
    rng = [c for c in f.must if c.key == "effective_date_ts"]
    assert rng and rng[0].range.gte == 1704067200.0
    assert applied["effective_date_from"] == "2024-01-01"


def test_profile_of_drops_nones():
    assert profile_of(_user(department="HR")) == {"department": "HR"}


def _access(f):
    return [c for c in f.must if c.key == "access_level"]


def test_employee_restricted_to_public():
    f, _ = build_qdrant_filter(_user(role="employee"), None, False)
    conds = _access(f)
    assert len(conds) == 1 and conds[0].match.value == "public"


def test_hr_manager_gets_public_and_internal():
    f, _ = build_qdrant_filter(_user(role="hr_manager"), None, False)
    conds = _access(f)
    assert len(conds) == 1 and sorted(conds[0].match.any) == ["internal", "public"]


def test_legal_gets_restricted_too():
    f, _ = build_qdrant_filter(_user(role="legal_counsel"), None, False)
    assert "restricted" in _access(f)[0].match.any


def test_admin_has_no_access_filter():
    f, _ = build_qdrant_filter(_user(role="admin"), None, False)
    assert _access(f) == []


def test_extract_filters_parses_json():
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": 'Intro {"location": "UK"} outro'}}]}
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = resp
    with patch("httpx.Client", return_value=client):
        out = extract_filters_llm("leave rules for UK staff?")
    assert out == {"location": "UK"}
    _, kwargs = client.post.call_args
    assert kwargs["json"]["temperature"] == 0.0


def test_extract_filters_unknown_keys_dropped():
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": '{"location": "UK", "salary": 5}'}}]}
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = resp
    with patch("httpx.Client", return_value=client):
        assert extract_filters_llm("q") == {"location": "UK"}


def test_extract_filters_failure_returns_empty():
    with patch("httpx.Client", side_effect=Exception("down")):
        assert extract_filters_llm("q") == {}
