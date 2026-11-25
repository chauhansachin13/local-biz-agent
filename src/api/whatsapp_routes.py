"""WhatsApp Business Concierge webhook & conversation history routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.concierge_agent import handle_whatsapp_message
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.agent_models import (
    WhatsAppInboundRequest,
    WhatsAppMessage,
    WhatsAppMessageResponse,
)

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp Concierge"])


@router.post("/{business_id}/message")
async def receive_whatsapp_message(
    business_id: int,
    payload: WhatsAppInboundRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Process an inbound WhatsApp message from a customer or business owner."""
    business = await get_business_or_404(db, business_id)
    result = await handle_whatsapp_message(
        db=db,
        business=business,
        sender_phone=payload.sender_phone,
        sender_name=payload.sender_name,
        sender_role=payload.sender_role,
        message_text=payload.message,
    )
    await db.commit()
    return result


@router.get("/{business_id}/messages", response_model=list[WhatsAppMessageResponse])
async def list_whatsapp_messages(
    business_id: int,
    limit: int = Query(default=40, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[WhatsAppMessage]:
    """Retrieve stored WhatsApp concierge messages for a business."""
    await get_business_or_404(db, business_id)
    stmt = (
        select(WhatsAppMessage)
        .where(WhatsAppMessage.business_id == business_id)
        .order_by(WhatsAppMessage.id.asc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())
