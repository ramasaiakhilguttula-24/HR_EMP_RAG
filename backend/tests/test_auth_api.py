"""API tests for /auth/* with mocked DB session + memory fallback for Redis.

No Docker needed: get_db is overridden, blacklist/rate-limit fall back to memory.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app.core import token_blacklist as tb
from backend.app.core.database import get_db
from backend.app.core.security import create_refresh_token, get_password_hash
from backend.app.main import app
from backend.app.models.user import User, UserRole


class FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


def make_user(email="emp@company.com", password="Strong123"):
    u = User(
        email=email,
        password_hash=get_password_hash(password),
        full_name="Test Emp",
        role=UserRole.employee,
        department="Engineering",
        location="India",
    )
    u.id = uuid.uuid4()
    u.is_active = True
    return u


def make_session(user):
    from unittest.mock import MagicMock

    session = AsyncMock()
    session.execute.return_value = FakeResult(user)
    session.add = MagicMock(return_value=None)
    session.commit.return_value = None

    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    session.refresh.side_effect = _refresh
    return session


@pytest.fixture(autouse=True)
def clean_state():
    import asyncio

    asyncio.run(tb.clear_test_state())
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    asyncio.run(tb.clear_test_state())


def client_with(user):
    async def _override():
        yield make_session(user)

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_register_success():
    c = client_with(None)  # no existing user
    r = c.post(
        "/api/v1/auth/register",
        json={"email": "new@company.com", "password": "Strong123", "full_name": "New Guy"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "new@company.com"


def test_register_duplicate_409():
    c = client_with(make_user(email="dup@company.com"))
    r = c.post(
        "/api/v1/auth/register",
        json={"email": "dup@company.com", "password": "Strong123", "full_name": "Dup"},
    )
    assert r.status_code == 409


def test_register_weak_password_422():
    c = client_with(None)
    r = c.post(
        "/api/v1/auth/register",
        json={"email": "w@company.com", "password": "weak", "full_name": "W"},
    )
    assert r.status_code == 422


def test_login_success_returns_pair():
    c = client_with(make_user())
    r = c.post("/api/v1/auth/login", json={"email": "emp@company.com", "password": "Strong123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password_401():
    c = client_with(make_user())
    r = c.post("/api/v1/auth/login", json={"email": "emp@company.com", "password": "Wrong1234"})
    assert r.status_code == 401


def test_login_lockout_after_5_failures():
    c = client_with(make_user())
    for _ in range(5):
        r = c.post("/api/v1/auth/login", json={"email": "emp@company.com", "password": "Wrong1234"})
        assert r.status_code == 401
    r = c.post("/api/v1/auth/login", json={"email": "emp@company.com", "password": "Wrong1234"})
    assert r.status_code == 429


def test_refresh_rotation_and_old_token_revoked():
    user = make_user()
    c = client_with(user)
    login = c.post("/api/v1/auth/login", json={"email": user.email, "password": "Strong123"})
    refresh = login.json()["refresh_token"]

    r1 = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r1.status_code == 200

    r2 = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401  # old token revoked after rotation


def test_logout_revokes_access_token():
    user = make_user()
    c = client_with(user)
    login = c.post("/api/v1/auth/login", json={"email": user.email, "password": "Strong123"})
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]

    r = c.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200

    # Reusing the same access token must now fail (blacklisted).
    r2 = c.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 401


def test_refresh_token_cannot_be_used_as_access():
    user = make_user()
    c = client_with(user)
    _, _, _ = None, None, None
    refresh, _, _ = create_refresh_token(str(user.id))
    r = c.post("/api/v1/auth/logout", json={}, headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401
