"""Unit tests for hashing, JWT, password policy. No DB/Redis needed."""
import time

import pytest
from jose import jwt

from backend.app.core.config import get_settings
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    validate_password_policy,
    verify_password,
)


def test_password_policy_accepts_strong():
    validate_password_policy("Strong123")


def test_password_policy_rejects_weak():
    for weak in ["short1A", "alllowercase1", "ALLUPPER1", "NoDigitsHere", "12345678"]:
        with pytest.raises(ValueError):
            validate_password_policy(weak)


def test_hash_verify_roundtrip():
    h = get_password_hash("Strong123")
    assert h != "Strong123"
    assert verify_password("Strong123", h)
    assert not verify_password("Wrong1234", h)


def test_access_token_shape_and_ttl():
    settings = get_settings()
    token, jti, _ = create_access_token("uid-1", "a@b.com", "employee")
    payload = decode_token(token)
    assert payload["sub"] == "uid-1"
    assert payload["type"] == "access"
    assert payload["jti"] == jti
    ttl = payload["exp"] - payload["iat"]
    assert abs(ttl - settings.ACCESS_TTL_MIN * 60) <= 2


def test_refresh_token_ttl():
    settings = get_settings()
    token, jti, _ = create_refresh_token("uid-1")
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    ttl = payload["exp"] - payload["iat"]
    assert abs(ttl - settings.REFRESH_TTL_DAYS * 86400) <= 2


def test_tampered_token_rejected():
    token, _, _ = create_access_token("uid-1", "a@b.com", "employee")
    with pytest.raises(Exception):
        decode_token(token + "tamper")


def test_expired_token_rejected():
    settings = get_settings()
    payload = {
        "sub": "uid-1",
        "type": "access",
        "jti": "x",
        "iat": int(time.time()) - 100,
        "exp": int(time.time()) - 10,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    with pytest.raises(Exception):
        decode_token(token)
