"""API routes for Loyalty Points, Gift Cards, NPS Surveys, Email Campaigns & Content Calendar."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.loyalty_and_engagement import (
    create_email_campaign,
    earn_loyalty_points,
    generate_content_calendar,
    get_campaign_analytics,
    get_content_calendar,
    get_email_campaign_preview_html,
    get_gift_card_info,
    get_loyalty_account_details,
    get_loyalty_analytics,
    get_loyalty_leaderboard,
    get_nps_analytics,
    get_or_create_loyalty_account,
    issue_gift_card,
    list_email_campaigns,
    list_gift_cards,
    list_nps_surveys,
    promote_calendar_entry_to_social,
    redeem_gift_card,
    redeem_loyalty_points,
    send_email_campaign,
    submit_nps_survey,
)
from src.database import get_db
from src.models.business import Business
from src.models.loyalty_models import (
    ContentCalendarCreate,
    ContentCalendarPromoteRequest,
    EmailCampaignCreate,
    GiftCardCreate,
    GiftCardRedeemRequest,
    LoyaltyAccountCreate,
    LoyaltyEarnRequest,
    LoyaltyRedeemRequest,
    NPSSurveyCreate,
)

router = APIRouter(prefix="/api/loyalty", tags=["Loyalty & Engagement"])


async def _get_business(business_id: int, db: AsyncSession) -> Business:
    result = await db.execute(select(Business).where(Business.id == business_id))
    biz = result.scalar_one_or_none()
    if biz is None:
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")
    return biz


# ---------------------------------------------------------------------------
# Loyalty Points
# ---------------------------------------------------------------------------


@router.post("/{business_id}/points/account", status_code=201)
async def create_loyalty_account(
    business_id: int, body: LoyaltyAccountCreate, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Create or retrieve a loyalty account for a customer."""
    await _get_business(business_id, db)
    account = await get_or_create_loyalty_account(
        db, business_id, body.customer_email, body.customer_name
    )
    await db.commit()
    return {
        "id": account.id,
        "customer_email": account.customer_email,
        "customer_name": account.customer_name,
        "points_balance": account.points_balance,
        "lifetime_points": account.lifetime_points,
        "tier": account.tier.value,
        "is_active": account.is_active,
    }


@router.post("/{business_id}/points/earn")
async def earn_points(
    business_id: int, body: LoyaltyEarnRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Award loyalty points to a customer."""
    await _get_business(business_id, db)
    result = await earn_loyalty_points(
        db, business_id, body.customer_email, "Customer", body.points, body.description
    )
    await db.commit()
    return result


@router.post("/{business_id}/points/redeem")
async def redeem_points(
    business_id: int, body: LoyaltyRedeemRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Redeem loyalty points for a discount."""
    await _get_business(business_id, db)
    result = await redeem_loyalty_points(
        db, business_id, body.customer_email, body.points, body.description
    )
    if not result.get("success", True) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await db.commit()
    return result


@router.get("/{business_id}/points/account")
async def get_loyalty_account(
    business_id: int,
    email: str = Query(..., min_length=3),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Look up a customer's loyalty balance, tier, and transaction history."""
    await _get_business(business_id, db)
    info = await get_loyalty_account_details(db, business_id, email)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Loyalty account not found for {email}")
    return info


@router.get("/{business_id}/points/leaderboard")
async def loyalty_leaderboard(
    business_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get top loyalty members ranked by lifetime points."""
    await _get_business(business_id, db)
    leaders = await get_loyalty_leaderboard(db, business_id, limit)
    return {"business_id": business_id, "leaderboard": leaders}


@router.get("/{business_id}/points/analytics")
async def loyalty_analytics(business_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Get loyalty program analytics and tier breakdown."""
    await _get_business(business_id, db)
    return await get_loyalty_analytics(db, business_id)


# ---------------------------------------------------------------------------
# Gift Cards
# ---------------------------------------------------------------------------


@router.post("/{business_id}/gift-cards", status_code=201)
async def create_gift_card(
    business_id: int, body: GiftCardCreate, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Issue a new digital gift card."""
    await _get_business(business_id, db)
    result = await issue_gift_card(
        db,
        business_id,
        body.amount,
        str(body.recipient_email) if body.recipient_email else None,
        body.recipient_name,
        str(body.sender_email) if body.sender_email else None,
        body.message,
        body.expires_days or 365,
    )
    await db.commit()
    return result


@router.get("/{business_id}/gift-cards")
async def list_business_gift_cards(
    business_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """List all digital gift cards issued by a business."""
    await _get_business(business_id, db)
    cards = await list_gift_cards(db, business_id)
    return {"business_id": business_id, "total": len(cards), "gift_cards": cards}


@router.get("/{business_id}/gift-cards/{code}")
async def get_gift_card(
    business_id: int, code: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Check gift card balance and status."""
    await _get_business(business_id, db)
    info = await get_gift_card_info(db, business_id, code)
    if info is None:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return info


@router.post("/{business_id}/gift-cards/redeem")
async def redeem_gift_card_route(
    business_id: int, body: GiftCardRedeemRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Redeem (partial or full) a gift card balance."""
    await _get_business(business_id, db)
    result = await redeem_gift_card(db, business_id, body.code, body.amount)
    if not result.get("success", True):
        raise HTTPException(status_code=400, detail=result["error"])
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# NPS Surveys
# ---------------------------------------------------------------------------


@router.post("/{business_id}/nps", status_code=201)
async def submit_nps(
    business_id: int, body: NPSSurveyCreate, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Submit an NPS survey response."""
    await _get_business(business_id, db)
    result = await submit_nps_survey(
        db,
        business_id,
        str(body.customer_email),
        body.score,
        body.feedback,
        body.customer_name,
        body.source or "widget",
    )
    await db.commit()
    return result


@router.get("/{business_id}/nps")
async def get_nps_responses(
    business_id: int,
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List recent NPS survey responses for a business."""
    await _get_business(business_id, db)
    surveys = await list_nps_surveys(db, business_id, limit=limit)
    return {"business_id": business_id, "total": len(surveys), "surveys": surveys}


@router.get("/{business_id}/nps/analytics")
async def nps_analytics(business_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Get NPS score, breakdown, and feedback themes."""
    await _get_business(business_id, db)
    return await get_nps_analytics(db, business_id)


# ---------------------------------------------------------------------------
# Email Campaigns
# ---------------------------------------------------------------------------


@router.post("/{business_id}/email-campaigns", status_code=201)
async def create_campaign(
    business_id: int, body: EmailCampaignCreate, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Create a new email campaign with optional template auto-generation."""
    biz = await _get_business(business_id, db)
    result = await create_email_campaign(
        db,
        biz,
        body.name,
        body.campaign_type,
        body.subject,
        body.body_html,
        body.target_segment or "all",
        body.scheduled_at,
    )
    await db.commit()
    return result


@router.post("/{business_id}/email-campaigns/{campaign_id}/send")
async def send_campaign(
    business_id: int, campaign_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Send an email campaign immediately."""
    await _get_business(business_id, db)
    result = await send_email_campaign(db, business_id, campaign_id)
    if not result.get("success", True):
        raise HTTPException(status_code=400, detail=result["error"])
    await db.commit()
    return result


@router.get("/{business_id}/email-campaigns")
async def get_campaigns(business_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """List all email campaigns for a business."""
    await _get_business(business_id, db)
    campaigns = await list_email_campaigns(db, business_id)
    return {"business_id": business_id, "total": len(campaigns), "campaigns": campaigns}


@router.get("/{business_id}/email-campaigns/{campaign_id}/preview", response_class=HTMLResponse)
async def preview_campaign_html(
    business_id: int, campaign_id: int, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Preview an email campaign as a rendered HTML document."""
    await _get_business(business_id, db)
    preview = await get_email_campaign_preview_html(db, business_id, campaign_id)
    if preview is None:
        raise HTTPException(status_code=404, detail=f"Email campaign {campaign_id} not found")
    return HTMLResponse(content=preview)


@router.get("/{business_id}/email-campaigns/analytics")
async def campaign_analytics(
    business_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Get aggregate email campaign analytics."""
    await _get_business(business_id, db)
    return await get_campaign_analytics(db, business_id)


# ---------------------------------------------------------------------------
# Content Calendar
# ---------------------------------------------------------------------------


@router.post("/{business_id}/content-calendar/generate", status_code=201)
async def generate_calendar(
    business_id: int, body: ContentCalendarCreate, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Generate an AI content calendar for the next N days."""
    biz = await _get_business(business_id, db)
    result = await generate_content_calendar(db, biz, body.days_ahead, body.platforms)
    await db.commit()
    return result


@router.get("/{business_id}/content-calendar")
async def get_calendar(
    business_id: int,
    platform: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get saved content calendar entries."""
    await _get_business(business_id, db)
    entries = await get_content_calendar(db, business_id, platform)
    return {"business_id": business_id, "total": len(entries), "entries": entries}


@router.post("/{business_id}/content-calendar/{entry_id}/promote")
async def promote_calendar_entry(
    business_id: int,
    entry_id: int,
    body: ContentCalendarPromoteRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Promote a planned content calendar entry into the SocialPost pipeline."""
    await _get_business(business_id, db)
    res = await promote_calendar_entry_to_social(
        db,
        business_id,
        entry_id,
        auto_publish=(body.auto_publish if body else False),
    )
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error", "Entry not found"))
    await db.commit()
    return res
