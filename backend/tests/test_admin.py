"""Admin role-management tests (F14) with mocked DB + mocked guard."""
import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role
from backend.app.main import app
from backend.app.models.user import User, UserRole


def _admin():
    u = User(email="a@c.com", password_hash="x", full_name="A", role=UserRole.admin)
    u.id = uuid.uuid4()
    u.is_active = True
    return u


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, single=None, items=None):
        self._single = single
        self._items = items or []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return FakeScalars(self._items)


def _client(single=None, items=None, user=None):
    session = AsyncMock()
    session.execute.return_value = FakeResult(single, items)
    session.add = MagicMock(return_value=None)
    session.commit.return_value = None
    session.refresh.return_value = None

    async def _db():
        yield session

    async def _user():
        return user or _admin()

    app.dependency_overrides[get_db] = _db
    # bypass JWT: tests target handler logic, guard logic is tested via require_role
    from backend.app.core import dependencies as deps

    real_guard = deps.get_current_user

    async def _u():
        return user or _admin()

    app.dependency_overrides[real_guard] = _u
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_users():
    u = _admin()
    c = _client(items=[u])
    r = c.get("/api/v1/admin/users")
    assert r.status_code == 200 and r.json()[0]["email"] == "a@c.com"


def test_set_role():
    target = User(email="e@c.com", password_hash="x", full_name="E", role=UserRole.employee)
    target.id = uuid.uuid4()
    target.is_active = True
    c = _client(single=target)
    r = c.patch(f"/api/v1/admin/users/{target.id}/role", json={"role": "hr_manager"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "hr_manager"
    assert target.role == UserRole.hr_manager


def test_set_role_404():
    c = _client(single=None)
    r = c.patch(f"/api/v1/admin/users/{uuid.uuid4()}/role", json={"role": "hr_manager"})
    assert r.status_code == 404


def test_employee_cannot_list_users():
    emp = User(email="e@c.com", password_hash="x", full_name="E", role=UserRole.employee)
    emp.id = uuid.uuid4()
    emp.is_active = True
    c = _client(items=[], user=emp)
    r = c.get("/api/v1/admin/users")
    assert r.status_code == 403


def test_overview_aggregates():
    admin = _admin()
    seq = [10, 250.0, 6, 4, 1]

    class S:
        def __init__(self, v):
            self.v = v

        def scalar(self):
            return self.v

        def one(self):
            return (100, 50)

        def all(self):
            return [("leaves?", 7)]

    async def ex(stmt):
        return S(seq.pop(0)) if seq else S(None)

    session = AsyncMock()
    session.execute.side_effect = ex

    async def _db():
        yield session

    async def _u():
        return admin

    from backend.app.core import dependencies as deps

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[deps.get_current_user] = _u
    r = TestClient(app).get("/api/v1/admin/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query_volume"] == 10
    assert body["cache_hit_rate"] == 0.6
    assert body["feedback"] == {"up": 4, "down": 1, "satisfaction": 0.8}
    assert body["tokens"] == {"in": 100, "out": 50}
    assert body["top_questions"] == [{"query": "leaves?", "count": 7}]
