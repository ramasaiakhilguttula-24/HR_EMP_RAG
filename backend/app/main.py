"""FastAPI application factory. Entry point: `uvicorn backend.main:app`."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import admin, agent, auth, chat, documents, health
from backend.app.core.config import get_settings

# Import models so SQLAlchemy registers tables for Alembic + create_all.
from backend.app.models import document, query_log, user  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001 - required lifespan signature
    """Ensure the vector collection + payload indexes exist (self-healing deploys)."""
    try:
        from backend.app.core.qdrant import ensure_collection

        await asyncio.to_thread(ensure_collection)
    except Exception as e:  # noqa: BLE001 - boot must never fail on index setup
        print(f"WARNING: Qdrant setup skipped: {type(e).__name__}")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

    # Browser frontend (F18) calls the API cross-origin in dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)  # GET /health, /ready (no prefix, stable for probes)
    app.include_router(auth.router, prefix=settings.API_PREFIX)
    app.include_router(documents.router, prefix=settings.API_PREFIX)
    app.include_router(chat.router, prefix=settings.API_PREFIX)
    app.include_router(agent.router, prefix=settings.API_PREFIX)
    app.include_router(admin.router, prefix=settings.API_PREFIX)
    return app


app = create_app()
