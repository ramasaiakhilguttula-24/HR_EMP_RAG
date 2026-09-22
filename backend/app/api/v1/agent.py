"""Agentic RAG endpoint (Feature 15): multi-step HR queries + escalation."""
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.chat import _guard_injection, _mask_query
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.query_log import QueryLog
from backend.app.models.user import User
from backend.app.schemas.chat import CitationOut
from backend.app.services.generation.agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class AgentStepOut(BaseModel):
    tool: str
    args: dict
    observation: dict


class AgentOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    steps: list[AgentStepOut]
    iterations: int
    escalated: bool
    latency_ms: int


@router.post("/chat", response_model=AgentOut)
async def agent_chat(
    body: AgentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    await _guard_injection(body.query, user, db)
    query = await _mask_query(body.query, user, db)
    res = await run_agent(query, user=user, db=db,
                            langsmith_extra={"metadata": {"user_id": str(user.id),
                                                          "role": user.role.value,
                                                          "endpoint": "agent"}})
    latency_ms = int((time.perf_counter() - started) * 1000)

    db.add(QueryLog(user_id=user.id, query=query,
                    normalized_query=query.strip().lower(), answer=res["answer"],
                    citations=res["citations"], latency_ms=latency_ms, cache_hit=False))
    await db.commit()
    return AgentOut(
        answer=res["answer"],
        citations=[CitationOut(index=i + 1, document=c["document"], page=c.get("page"),
                               section=None, excerpt=c.get("excerpt", ""))
                   for i, c in enumerate(res["citations"])],
        steps=[AgentStepOut(tool=s["tool"], args=s["args"], observation=s["observation"])
               for s in res["steps"]],
        iterations=res["iterations"], escalated=res["escalated"], latency_ms=latency_ms,
    )
