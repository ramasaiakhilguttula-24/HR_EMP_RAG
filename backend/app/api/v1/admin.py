"""Admin routes: user management (F14). All endpoints admin-only."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import require_role
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


class RolePatch(BaseModel):
    role: UserRole

def _out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email, full_name=u.full_name,
                   role=u.role.value, department=u.department, location=u.location)


@router.get("/users", response_model=list[UserOut])
async def list_users(user: User = Depends(require_role("admin")),
                     db: AsyncSession = Depends(get_db)):
    _ = user  # authenticated + authorized via guard
    rows = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [_out(u) for u in rows]


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_role(user_id: str, body: RolePatch,
                   user: User = Depends(require_role("admin")),
                   db: AsyncSession = Depends(get_db)):
    _ = user
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid user id")
    target = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    target.role = body.role
    await db.commit()
    await db.refresh(target)
    return _out(target)


@router.get("/overview")
async def overview(user: User = Depends(require_role("admin", "hr_manager")),
                   db: AsyncSession = Depends(get_db)):
    """Real analytics + monitoring aggregates from query_logs (F18 dashboards)."""
    from sqlalchemy import func

    from backend.app.models.query_log import QueryLog

    _ = user
    total = (await db.execute(select(func.count(QueryLog.id)))).scalar() or 0
    avg_latency = (await db.execute(select(func.avg(QueryLog.latency_ms)))).scalar() or 0
    cache_hits = (await db.execute(
        select(func.count(QueryLog.id)).where(QueryLog.cache_hit.is_(True)))).scalar() or 0
    up = (await db.execute(select(func.count(QueryLog.id)).where(QueryLog.feedback == 1))).scalar() or 0
    down = (await db.execute(select(func.count(QueryLog.id)).where(QueryLog.feedback == -1))).scalar() or 0
    tokens = (await db.execute(
        select(func.coalesce(func.sum(QueryLog.tokens_in), 0),
               func.coalesce(func.sum(QueryLog.tokens_out), 0)))).one()
    top_rows = (await db.execute(
        select(QueryLog.normalized_query, func.count(QueryLog.id).label("n"))
        .where(QueryLog.normalized_query.is_not(None))
        .group_by(QueryLog.normalized_query).order_by(func.count(QueryLog.id).desc()).limit(5)
    )).all()
    return {
        "query_volume": total,
        "avg_latency_ms": round(float(avg_latency), 1),
        "cache_hit_rate": round(cache_hits / total, 3) if total else 0.0,
        "feedback": {"up": up, "down": down,
                     "satisfaction": round(up / (up + down), 3) if (up + down) else None},
        "tokens": {"in": int(tokens[0]), "out": int(tokens[1])},
        "top_questions": [{"query": q, "count": n} for q, n in top_rows],
    }
