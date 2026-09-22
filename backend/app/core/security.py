"""Password hashing + JWT helpers (Feature 3).

Strategy: short-lived access token (15 min) + long-lived refresh token (7 days)
with rotation. Revoked JTIs are stored in Redis (see token_blacklist.py).
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.core.config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Minimum 8 chars, at least one upper, one lower, one digit.
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def validate_password_policy(password: str) -> None:
    """Raise ValueError if password does not meet policy."""
    if not _PASSWORD_RE.match(password):
        raise ValueError(
            "Password must be >=8 chars with upper, lower and digit."
        )


def get_password_hash(password: str) -> str:
    return _pwd.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, email: str, role: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    settings = get_settings()
    jti = str(uuid.uuid4())
    expires = _now() + timedelta(minutes=settings.ACCESS_TTL_MIN)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "jti": jti,
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG), jti, expires


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    settings = get_settings()
    jti = str(uuid.uuid4())
    expires = _now() + timedelta(days=settings.REFRESH_TTL_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG), jti, expires


def decode_token(token: str) -> dict:
    """Verify signature + expiry. Raises JWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])


def remaining_ttl_seconds(payload: dict) -> int:
    exp = int(payload.get("exp", 0))
    return max(0, exp - int(_now().timestamp()))
