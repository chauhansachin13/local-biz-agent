"""AI Orchestrator chat and proactive business suggestions routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.orchestrator import BizPresenceOrchestrator
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.api_schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentSuggestion,
    AgentSuggestionsResponse,
)

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])
orchestrator = BizPresenceOrchestrator()


@router.post("/{business_id}/chat", response_model=AgentChatResponse)
async def chat_with_agent(
    business_id: int,
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentChatResponse:
    """Send a natural-language message to the BizPresence AI orchestrator."""
    business = await get_business_or_404(db, business_id)
    result = await orchestrator.handle_chat(
        db=db,
        business=business,
        message=payload.message,
        auto_execute=payload.auto_execute,
        context=payload.context,
    )
    await db.commit()
    return AgentChatResponse(**result)


@router.get("/{business_id}/suggestions", response_model=AgentSuggestionsResponse)
async def get_agent_suggestions(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> AgentSuggestionsResponse:
    """Return AI-generated proactive recommendations for the business."""
    business = await get_business_or_404(db, business_id)
    raw = await orchestrator.generate_suggestions(db=db, business=business)
    return AgentSuggestionsResponse(
        business_id=business_id,
        generated_at=datetime.now(timezone.utc),
        suggestions=[AgentSuggestion(**item) for item in raw],
    )
