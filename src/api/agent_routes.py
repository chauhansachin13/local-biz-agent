"""AI Orchestrator chat, HITL approvals, autopilot, magic onboarding, and campaign routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import (
    compute_health_score,
    get_or_create_agent_config,
    launch_multi_channel_campaign,
    run_magic_onboarding,
)
from src.agents.orchestrator import BizPresenceOrchestrator
from src.agents.scheduler import run_autopilot_cycle_for_business
from src.agents.seo_audit import generate_daily_brief, run_seo_and_sentiment_audit
from src.agents.strategy_council import get_upcoming_festivals, run_strategy_council
from src.agents.supervisor import decide_approval_action
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.agent_models import (
    AgentApprovalAction,
    AgentApprovalResponse,
    AgentRunLog,
    AgentRunLogResponse,
    AgentThreadMessage,
    AgentThreadMessageResponse,
    ApprovalDecisionRequest,
    ApprovalStatus,
    BusinessAgentConfigResponse,
    BusinessAgentConfigUpdate,
)
from src.models.api_schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentSuggestion,
    AgentSuggestionsResponse,
    CampaignRequest,
    CampaignResponse,
    MagicOnboardRequest,
    MagicOnboardResponse,
    PresenceHealthScoreResponse,
)

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])
orchestrator = BizPresenceOrchestrator()


@router.post(
    "/magic-onboard",
    response_model=MagicOnboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def magic_onboard_business(
    payload: MagicOnboardRequest,
    db: AsyncSession = Depends(get_db),
) -> MagicOnboardResponse:
    """Launch a complete local business digital presence in one click."""
    result = await run_magic_onboarding(db=db, payload_dict=payload.model_dump())
    await db.commit()
    return MagicOnboardResponse(**result)


@router.post("/{business_id}/chat", response_model=AgentChatResponse)
async def chat_with_agent(
    business_id: int,
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentChatResponse:
    """Send a natural-language request to the LangGraph BizPresence AI supervisor."""
    business = await get_business_or_404(db, business_id)
    result = await orchestrator.handle_chat(
        db=db,
        business=business,
        message=payload.message,
        auto_execute=payload.auto_execute,
        session_id=payload.session_id,
        language=payload.language,
        context=payload.context,
    )
    await db.commit()
    return AgentChatResponse(**result)


@router.get("/{business_id}/history", response_model=list[AgentThreadMessageResponse])
async def get_chat_history(
    business_id: int,
    session_id: str = Query(default="default"),
    limit: int = Query(default=40, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AgentThreadMessage]:
    """Retrieve persistent conversation history for a business chat session."""
    await get_business_or_404(db, business_id)
    stmt = (
        select(AgentThreadMessage)
        .where(
            AgentThreadMessage.business_id == business_id,
            AgentThreadMessage.session_id == session_id,
        )
        .order_by(AgentThreadMessage.id.asc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.delete("/{business_id}/history")
async def clear_chat_history(
    business_id: int,
    session_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Clear stored chat history for a business session."""
    await get_business_or_404(db, business_id)
    await db.execute(
        delete(AgentThreadMessage).where(
            AgentThreadMessage.business_id == business_id,
            AgentThreadMessage.session_id == session_id,
        )
    )
    await db.commit()
    return {"status": "cleared", "session_id": session_id}


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
        generated_at=datetime.now(UTC),
        suggestions=[AgentSuggestion(**item) for item in raw],
    )


@router.get("/{business_id}/health-score", response_model=PresenceHealthScoreResponse)
async def get_presence_health_score(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> PresenceHealthScoreResponse:
    """Compute a 0-100 Digital Presence Health Score across 5 business pillars."""
    business = await get_business_or_404(db, business_id)
    score = await compute_health_score(db, business)
    await db.commit()
    return PresenceHealthScoreResponse(**score)


@router.get("/{business_id}/approvals", response_model=list[AgentApprovalResponse])
async def list_approval_actions(
    business_id: int,
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[AgentApprovalAction]:
    """List Human-in-the-Loop (HITL) pending/decided AI actions."""
    await get_business_or_404(db, business_id)
    stmt = select(AgentApprovalAction).where(AgentApprovalAction.business_id == business_id)
    if approval_status is not None:
        stmt = stmt.where(AgentApprovalAction.status == approval_status)
    stmt = stmt.order_by(AgentApprovalAction.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.post(
    "/{business_id}/approvals/{action_id}/decide",
    response_model=AgentApprovalResponse,
)
async def decide_approval(
    business_id: int,
    action_id: int,
    payload: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentApprovalAction:
    """Approve (optionally editing content) or reject a queued HITL agent action."""
    business = await get_business_or_404(db, business_id)
    stmt = select(AgentApprovalAction).where(
        AgentApprovalAction.id == action_id,
        AgentApprovalAction.business_id == business_id,
    )
    action = (await db.execute(stmt)).scalar_one_or_none()
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval action {action_id} not found for business {business_id}",
        )
    if action.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval action {action_id} is already {action.status.value}",
        )

    updated = await decide_approval_action(
        db=db,
        business=business,
        action=action,
        decision=payload.decision,
        edited_content=payload.edited_content,
    )
    await db.commit()
    await db.refresh(updated)
    return updated


@router.get("/{business_id}/logs", response_model=list[AgentRunLogResponse])
async def list_agent_run_logs(
    business_id: int,
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunLog]:
    """List multi-agent execution logs and tool traces."""
    await get_business_or_404(db, business_id)
    stmt = (
        select(AgentRunLog)
        .where(AgentRunLog.business_id == business_id)
        .order_by(AgentRunLog.id.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{business_id}/autopilot", response_model=BusinessAgentConfigResponse)
async def get_autopilot_config(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> BusinessAgentConfigResponse:
    """Get autopilot rules, language, voice, and catalog config for a business."""
    await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    await db.commit()
    await db.refresh(cfg)
    return BusinessAgentConfigResponse.model_validate(cfg)


@router.put("/{business_id}/autopilot", response_model=BusinessAgentConfigResponse)
async def update_autopilot_config(
    business_id: int,
    payload: BusinessAgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> BusinessAgentConfigResponse:
    """Update autopilot rules, preferred language, brand voice, or catalog items."""
    await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    return BusinessAgentConfigResponse.model_validate(cfg)


@router.post("/{business_id}/autopilot/run")
async def trigger_autopilot_cycle(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually trigger an autonomous autopilot cycle for a business."""
    business = await get_business_or_404(db, business_id)
    result = await run_autopilot_cycle_for_business(db, business)
    await db.commit()
    return result


@router.post("/{business_id}/campaign", response_model=CampaignResponse)
async def create_multi_channel_campaign(
    business_id: int,
    payload: CampaignRequest,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    """Generate a coordinated multi-platform marketing campaign."""
    business = await get_business_or_404(db, business_id)
    result = await launch_multi_channel_campaign(
        db=db,
        business=business,
        occasion=payload.occasion,
        offer_details=payload.offer_details,
        platforms=payload.platforms,
        auto_execute=payload.auto_execute,
        schedule_start_days=payload.schedule_start_days,
    )
    await db.commit()
    return CampaignResponse(**result)


@router.get("/{business_id}/seo-audit")
async def get_seo_and_sentiment_audit(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run local SEO NAP check, keyword targeting, and review theme extraction."""
    business = await get_business_or_404(db, business_id)
    audit = await run_seo_and_sentiment_audit(db, business)
    await db.commit()
    return audit


@router.get("/{business_id}/daily-brief")
async def get_morning_daily_brief(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return an executive Morning AI Briefing for the business owner."""
    business = await get_business_or_404(db, business_id)
    brief = await generate_daily_brief(db, business)
    await db.commit()
    return brief


@router.post("/{business_id}/strategy-council")
async def run_weekly_strategy_council(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run the 3-agent collaborative Strategy Council debate & weekly action plan."""
    business = await get_business_or_404(db, business_id)
    result = await run_strategy_council(db, business)
    await db.commit()
    return result


@router.get("/{business_id}/festivals")
async def list_upcoming_festivals(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return upcoming seasonal & local marketing campaign windows."""
    business = await get_business_or_404(db, business_id)
    return get_upcoming_festivals(business)


class VoiceCommandRequest(BaseModel):
    """Voice-to-text command payload from browser microphone or audio transcript."""

    transcript: str = Field(..., min_length=1)
    auto_execute: bool = True
    language: str | None = None


@router.post("/{business_id}/voice-command", response_model=AgentChatResponse)
async def handle_voice_command(
    business_id: int,
    payload: VoiceCommandRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentChatResponse:
    """Route a spoken voice command transcript through the LangGraph Supervisor."""
    business = await get_business_or_404(db, business_id)
    result = await orchestrator.handle_chat(
        db=db,
        business=business,
        message=payload.transcript,
        auto_execute=payload.auto_execute,
        session_id=f"voice_{business_id}",
        language=payload.language,
    )
    await db.commit()
    return AgentChatResponse(**result)
