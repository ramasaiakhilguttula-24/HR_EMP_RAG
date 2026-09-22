"""Shared FastAPI dependencies. Extended in Feature 14 (RBAC)."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db  # noqa: F401  (re-export for routers)
from backend.app.core.security import decode_token
from backend.app.core.token_blacklist import is_blacklisted
from backend.app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")
    if await is_blacklisted(payload.get("jti", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_role(*roles: str):
    """Usage: Depends(require_role('hr_manager', 'admin')). Denials are audit-logged."""
    async def _guard(user: User = Depends(get_current_user)) -> User:
        allowed = {r.lower() for r in roles}
        if user.role.value.lower() not in allowed and user.role.value != "admin":
            await _audit_deny(user, f"role in {sorted(allowed)}")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _guard


async def _audit_deny(user: User, required: str) -> None:
    """Best-effort RBAC denial audit (never breaks the request path)."""
    try:
        from backend.app.core.database import AsyncSessionLocal
        from backend.app.models.query_log import SecurityEvent, SecurityEventType

        async with AsyncSessionLocal() as db:
            db.add(SecurityEvent(user_id=user.id, event_type=SecurityEventType.rbac_denied,
                                 details={"required": required, "role": user.role.value}))
            await db.commit()
    except Exception:
        pass
