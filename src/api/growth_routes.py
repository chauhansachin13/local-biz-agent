"""Promo coupons, FAQ knowledge base, waitlist, broadcasts, localization, and revenue ROI routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import get_or_create_agent_config
from src.agents.revenue_and_growth import (
    compute_revenue_analytics,
    launch_segmented_broadcast,
    localize_content,
    suggest_business_faqs,
    validate_and_compute_discount,
)
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.growth_models import (
    BroadcastRequest,
    BroadcastResponse,
    CouponCreateRequest,
    CouponOffer,
    CouponResponse,
    CouponUpdateRequest,
    CouponValidateRequest,
    CouponValidateResponse,
    FaqListUpdateRequest,
    TranslateRequest,
    TranslateResponse,
    WaitlistCreateRequest,
    WaitlistEntry,
    WaitlistResponse,
    WaitlistStatus,
    WaitlistStatusUpdate,
)

router = APIRouter(prefix="/api/growth", tags=["Growth, Coupons & ROI"])


# ---------------------------------------------------------------------------
# Promo Coupons Engine
# ---------------------------------------------------------------------------


@router.get("/{business_id}/coupons", response_model=list[CouponResponse])
async def list_coupons(
    business_id: int,
    active_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[CouponOffer]:
    """List promotional coupon codes for a business."""
    await get_business_or_404(db, business_id)
    stmt = select(CouponOffer).where(CouponOffer.business_id == business_id)
    if active_only:
        stmt = stmt.where(CouponOffer.is_active.is_(True))
    stmt = stmt.order_by(CouponOffer.created_at.desc())
    rows = list((await db.execute(stmt)).scalars().all())
    if active_only:
        today = date.today()
        rows = [
            c
            for c in rows
            if (c.valid_until is None or c.valid_until >= today) and c.uses_count < c.max_uses
        ]
    return rows


@router.post(
    "/{business_id}/coupons",
    response_model=CouponResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_coupon(
    business_id: int,
    payload: CouponCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> CouponOffer:
    """Create a validated promotional coupon code for checkout & campaigns."""
    await get_business_or_404(db, business_id)
    existing = (
        await db.execute(
            select(CouponOffer).where(
                CouponOffer.business_id == business_id,
                CouponOffer.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Coupon code '{payload.code}' already exists for this business.",
        )

    coupon = CouponOffer(
        business_id=business_id,
        code=payload.code,
        title=payload.title.strip(),
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        min_order_amount=payload.min_order_amount,
        max_uses=payload.max_uses,
        valid_until=payload.valid_until,
        is_active=payload.is_active,
    )
    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)
    return coupon


@router.patch("/{business_id}/coupons/{coupon_id}", response_model=CouponResponse)
async def update_coupon(
    business_id: int,
    coupon_id: int,
    payload: CouponUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> CouponOffer:
    """Enable, disable, or extend an existing coupon offer."""
    await get_business_or_404(db, business_id)
    coupon = (
        await db.execute(
            select(CouponOffer).where(
                CouponOffer.id == coupon_id,
                CouponOffer.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if coupon is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coupon {coupon_id} not found for business {business_id}",
        )
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(coupon, field, val)
    await db.commit()
    await db.refresh(coupon)
    return coupon


@router.delete("/{business_id}/coupons/{coupon_id}")
async def delete_coupon(
    business_id: int,
    coupon_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a coupon offer."""
    await get_business_or_404(db, business_id)
    coupon = (
        await db.execute(
            select(CouponOffer).where(
                CouponOffer.id == coupon_id,
                CouponOffer.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if coupon is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coupon {coupon_id} not found for business {business_id}",
        )
    await db.delete(coupon)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{business_id}/coupons/validate", response_model=CouponValidateResponse)
async def preview_coupon_discount(
    business_id: int,
    payload: CouponValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> CouponValidateResponse:
    """Validate a coupon against a cart subtotal and return exact savings."""
    await get_business_or_404(db, business_id)
    res = await validate_and_compute_discount(
        db, business_id, payload.code, payload.subtotal, increment_use=False
    )
    coupon_obj = res.get("coupon")
    return CouponValidateResponse(
        valid=res["valid"],
        code=res["code"],
        subtotal=res["subtotal"],
        discount_amount=res["discount_amount"],
        final_total=res["final_total"],
        reason=res["reason"],
        coupon=CouponResponse.model_validate(coupon_obj) if coupon_obj else None,
    )


# ---------------------------------------------------------------------------
# Customer Waitlist Engine
# ---------------------------------------------------------------------------


@router.get("/{business_id}/waitlist", response_model=list[WaitlistResponse])
async def list_waitlist(
    business_id: int,
    wait_status: WaitlistStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[WaitlistEntry]:
    """List booking waitlist entries for a business."""
    await get_business_or_404(db, business_id)
    stmt = select(WaitlistEntry).where(WaitlistEntry.business_id == business_id)
    if wait_status is not None:
        stmt = stmt.where(WaitlistEntry.status == wait_status)
    stmt = stmt.order_by(WaitlistEntry.preferred_date.asc(), WaitlistEntry.created_at.asc())
    return list((await db.execute(stmt)).scalars().all())


@router.post(
    "/{business_id}/waitlist",
    response_model=WaitlistResponse,
    status_code=status.HTTP_201_CREATED,
)
async def join_waitlist(
    business_id: int,
    payload: WaitlistCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> WaitlistEntry:
    """Add a customer onto the smart booking waitlist."""
    await get_business_or_404(db, business_id)
    entry = WaitlistEntry(
        business_id=business_id,
        customer_name=payload.customer_name.strip(),
        customer_phone=payload.customer_phone.strip(),
        preferred_date=payload.preferred_date,
        preferred_time=payload.preferred_time,
        service=payload.service.strip(),
        status=WaitlistStatus.WAITING,
        notes=payload.notes,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.patch("/{business_id}/waitlist/{entry_id}", response_model=WaitlistResponse)
async def update_waitlist_status(
    business_id: int,
    entry_id: int,
    payload: WaitlistStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> WaitlistEntry:
    """Update waitlist entry status (e.g. booked or cancelled)."""
    await get_business_or_404(db, business_id)
    entry = (
        await db.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.id == entry_id,
                WaitlistEntry.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Waitlist entry {entry_id} not found",
        )
    entry.status = payload.status
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{business_id}/waitlist/{entry_id}")
async def delete_waitlist_entry(
    business_id: int,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Remove a customer from the waitlist."""
    await get_business_or_404(db, business_id)
    entry = (
        await db.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.id == entry_id,
                WaitlistEntry.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Waitlist entry {entry_id} not found",
        )
    await db.delete(entry)
    await db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Grounded FAQ Knowledge Base
# ---------------------------------------------------------------------------


@router.get("/{business_id}/faqs")
async def get_faqs(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Retrieve grounded concierge FAQs for a business."""
    await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    await db.commit()
    return list(cfg.faqs or [])


@router.put("/{business_id}/faqs")
async def replace_faqs(
    business_id: int,
    payload: FaqListUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Save the FAQ knowledge base used by the WhatsApp & Web concierge."""
    await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    cfg.faqs = [{"q": item.q.strip(), "a": item.a.strip()} for item in payload.faqs]
    await db.commit()
    return list(cfg.faqs)


@router.post("/{business_id}/faqs/suggest")
async def generate_suggested_faqs(
    business_id: int,
    apply: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AI-generate starter FAQs grounded in the business's real profile and catalog."""
    business = await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    suggested = await suggest_business_faqs(business, cfg)
    if apply:
        cfg.faqs = suggested
    await db.commit()
    return {"business_id": business_id, "applied": apply, "faqs": suggested}


# ---------------------------------------------------------------------------
# Segmented Broadcast, Revenue ROI & Localization
# ---------------------------------------------------------------------------


@router.post("/{business_id}/broadcast", response_model=BroadcastResponse)
async def run_segmented_broadcast(
    business_id: int,
    payload: BroadcastRequest,
    db: AsyncSession = Depends(get_db),
) -> BroadcastResponse:
    """Send or queue a CRM-segmented WhatsApp promotional broadcast."""
    business = await get_business_or_404(db, business_id)
    try:
        res = await launch_segmented_broadcast(
            db=db,
            business=business,
            segment=payload.segment,
            topic=payload.topic,
            promo_code=payload.promo_code,
            auto_execute=payload.auto_execute,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return BroadcastResponse(**res)


@router.get("/{business_id}/revenue-analytics")
async def get_revenue_and_roi_analytics(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return real order revenue, estimated booking value, top items, and repeat customer KPIs."""
    business = await get_business_or_404(db, business_id)
    res = await compute_revenue_analytics(db, business)
    await db.commit()
    return res


@router.post("/{business_id}/translate", response_model=TranslateResponse)
async def translate_business_copy(
    business_id: int,
    payload: TranslateRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslateResponse:
    """Translate or localize promotional text or replies into another language."""
    business = await get_business_or_404(db, business_id)
    res = await localize_content(business, payload.text, payload.target_language)
    return TranslateResponse(**res)
