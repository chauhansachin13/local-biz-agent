"""Customer CRM, Loyalty Retention, and Competitor Benchmarking routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.crm_and_competitors import (
    analyze_competitors,
    draft_retention_campaigns,
    sync_customers_from_activity,
)
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.agent_models import (
    CompetitorBenchmark,
    CompetitorCreateRequest,
    CompetitorResponse,
    CustomerCreateRequest,
    CustomerProfile,
    CustomerProfileResponse,
)

router = APIRouter(prefix="/api/crm", tags=["CRM & Competitors"])


@router.get("/{business_id}/customers", response_model=list[CustomerProfileResponse])
async def list_crm_customers(
    business_id: int,
    sync: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerProfile]:
    """List CRM customer profiles, syncing automatically from bookings/orders/reviews."""
    await get_business_or_404(db, business_id)
    if sync:
        customers = await sync_customers_from_activity(db, business_id)
        await db.commit()
        return customers
    stmt = (
        select(CustomerProfile)
        .where(CustomerProfile.business_id == business_id)
        .order_by(CustomerProfile.total_spent.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post(
    "/{business_id}/customers",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_crm_customer(
    business_id: int,
    payload: CustomerCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> CustomerProfile:
    """Manually add a customer to the business CRM."""
    await get_business_or_404(db, business_id)
    cust = CustomerProfile(
        business_id=business_id,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        segment=payload.segment,
        notes=payload.notes,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)
    return cust


@router.post("/{business_id}/retention-offers")
async def generate_retention_offers(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Queue personalized VIP & retention WhatsApp offers into the HITL Approval Inbox."""
    business = await get_business_or_404(db, business_id)
    result = await draft_retention_campaigns(db, business)
    await db.commit()
    return result


@router.get("/{business_id}/competitors")
async def get_competitor_intelligence(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Analyze tracked local competitors and recommend counter-positioning strategies."""
    business = await get_business_or_404(db, business_id)
    return await analyze_competitors(db, business)


@router.post(
    "/{business_id}/competitors",
    response_model=CompetitorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_competitor(
    business_id: int,
    payload: CompetitorCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> CompetitorBenchmark:
    """Add a nearby competitor to monitor."""
    await get_business_or_404(db, business_id)
    comp = CompetitorBenchmark(
        business_id=business_id,
        name=payload.name,
        category=payload.category,
        rating=payload.rating,
        review_count=payload.review_count,
        price_tier=payload.price_tier,
        strengths=payload.strengths,
        weaknesses=payload.weaknesses,
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@router.delete("/{business_id}/competitors/{competitor_id}")
async def delete_competitor(
    business_id: int,
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Remove a tracked competitor."""
    await get_business_or_404(db, business_id)
    stmt = select(CompetitorBenchmark).where(
        CompetitorBenchmark.id == competitor_id,
        CompetitorBenchmark.business_id == business_id,
    )
    comp = (await db.execute(stmt)).scalar_one_or_none()
    if not comp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor {competitor_id} not found",
        )
    await db.delete(comp)
    await db.commit()
    return {"status": "deleted"}
