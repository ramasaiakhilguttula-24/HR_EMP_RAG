"""Auth routes (Feature 3): register / login / refresh / logout.

Email verification is stubbed (no SMTP in learning phase).
SSO (Azure AD/Okta) is intentionally out of scope here.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    remaining_ttl_seconds,
    validate_password_policy,
    verify_password,
)
from backend.app.core.token_blacklist import (
    blacklist_jti,
    is_blacklisted,
    is_login_locked,
    record_failed_login,
    reset_login_attempts,
)
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import LoginIn, LogoutIn, RefreshIn, RegisterIn, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_out(user: User) -> UserOut:
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role or "employee")
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=role,
        department=user.department,
        location=user.location,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    try:
        validate_password_policy(body.password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    existing = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=body.email.lower(),
        password_hash=get_password_hash(body.password),
        full_name=body.full_name,
        role=UserRole.employee,
        department=body.department,
        location=body.location,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _to_out(user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    if await is_login_locked(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in 15 minutes.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        await record_failed_login(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account inactive")

    await reset_login_attempts(email)
    access, _, _ = create_access_token(str(user.id), user.email, user.role.value)
    refresh, _, _ = create_refresh_token(str(user.id))
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    if await is_blacklisted(payload.get("jti", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    # Rotation: revoke old refresh token, issue new pair.
    await blacklist_jti(payload["jti"], remaining_ttl_seconds(payload))
    access, _, _ = create_access_token(str(user.id), user.email, user.role.value)
    new_refresh, _, _ = create_refresh_token(str(user.id))
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(
    body: LogoutIn,
    creds: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    user: User = Depends(get_current_user),  # noqa: ARG001 - validates token + user
):
    """Blacklist current access token + supplied refresh token (rotation-safe)."""
    try:
        access_payload = decode_token(creds.credentials)
        await blacklist_jti(access_payload.get("jti", ""), remaining_ttl_seconds(access_payload))
    except JWTError:
        pass
    if body.refresh_token:
        try:
            payload = decode_token(body.refresh_token)
            await blacklist_jti(payload.get("jti", ""), remaining_ttl_seconds(payload))
        except JWTError:
            pass
    return {"status": "logged out"}
