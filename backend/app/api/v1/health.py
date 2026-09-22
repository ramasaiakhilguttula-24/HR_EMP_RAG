"""Liveness + readiness probes for Docker/K8s."""
import asyncio

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    """Liveness: is the process running? No external deps."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Readiness: can we serve traffic? Checks Postgres, Qdrant, Redis."""
    from backend.app.core.config import get_settings

    settings = get_settings()
    checks: dict[str, str] = {}

    # Postgres
    try:
        from backend.app.core.database import engine

        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3)
        checks["postgres"] = "up"
    except Exception as e:  # noqa: BLE001 - report reason, stay up for learning
        checks["postgres"] = f"down: {type(e).__name__}"

    # Qdrant
    try:
        from backend.app.core.qdrant import get_qdrant_client

        client = get_qdrant_client()
        await asyncio.to_thread(client.get_collections)
        checks["qdrant"] = "up"
    except Exception as e:  # noqa: BLE001
        checks["qdrant"] = f"down: {type(e).__name__}"

    # Redis
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        await asyncio.wait_for(r.ping(), timeout=3)
        await r.aclose()
        checks["redis"] = "up"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"down: {type(e).__name__}"

    degraded = any(v != "up" for v in checks.values())
    return {
        "status": "degraded" if degraded else "ready",
        "env": settings.ENV,
        "checks": checks,
    }
