"""Business profile, Google Business setup, and dashboard overview routes."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.api_schemas import (
    ActivityItem,
    DashboardOverviewResponse,
    GoogleSetupRequest,
    GoogleSetupResponse,
)
from src.models.booking import Booking, BookingStatus
from src.models.business import (
    Business,
    BusinessCreate,
    BusinessResponse,
    BusinessUpdate,
)
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPost

router = APIRouter(prefix="/api/businesses", tags=["Businesses"])


@router.get("/", response_model=list[BusinessResponse])
async def list_businesses(db: AsyncSession = Depends(get_db)) -> list[Business]:
    """List all registered local businesses."""
    result = await db.execute(select(Business).order_by(Business.id.asc()))
    return list(result.scalars().all())


@router.post("/", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
async def register_business(
    payload: BusinessCreate,
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Register a new local business profile."""
    business = Business(**payload.model_dump())
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Get business details by ID."""
    return await get_business_or_404(db, business_id)


@router.put("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: int,
    payload: BusinessUpdate,
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Update an existing business profile."""
    business = await get_business_or_404(db, business_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    await db.commit()
    await db.refresh(business)
    return business


@router.post("/{business_id}/setup-google", response_model=GoogleSetupResponse)
async def setup_google_profile(
    business_id: int,
    payload: GoogleSetupRequest,
    db: AsyncSession = Depends(get_db),
) -> GoogleSetupResponse:
    """Configure and verify Google Business Profile linkage for a business."""
    business = await get_business_or_404(db, business_id)

    gbp_id = (
        payload.google_business_id or business.google_business_id or f"ChIJ_{uuid.uuid4().hex[:14]}"
    )
    checklist = [
        {
            "item": "Business name & category",
            "completed": bool(business.name and business.category),
        },
        {
            "item": "Physical address / service area",
            "completed": bool(business.address or payload.service_area),
        },
        {"item": "Phone & website", "completed": bool(business.phone or business.website)},
        {"item": "Operating hours configured", "completed": bool(business.operating_hours)},
        {"item": "Google Business ID linked", "completed": bool(gbp_id)},
    ]
    completed_count = sum(1 for item in checklist if item["completed"])
    completeness_score = int((completed_count / len(checklist)) * 100)
    gbp_status = (
        "verified" if payload.verify_now and completeness_score >= 80 else "pending_verification"
    )

    business.google_business_id = gbp_id
    if payload.primary_category:
        business.category = payload.primary_category
    await db.commit()
    await db.refresh(business)

    return GoogleSetupResponse(
        business_id=business.id,
        google_business_id=gbp_id,
        status=gbp_status,
        completeness_score=completeness_score,
        checklist=checklist,
    )


@router.get("/{business_id}/dashboard", response_model=DashboardOverviewResponse)
async def get_business_dashboard(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewResponse:
    """Return aggregated metrics and recent activity feed for the dashboard overview."""
    business = await get_business_or_404(db, business_id)

    reviews = list(
        (
            await db.execute(
                select(Review)
                .where(Review.business_id == business_id)
                .order_by(Review.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    posts = list(
        (
            await db.execute(
                select(SocialPost)
                .where(SocialPost.business_id == business_id)
                .order_by(SocialPost.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    bookings = list(
        (
            await db.execute(
                select(Booking)
                .where(Booking.business_id == business_id)
                .order_by(Booking.booking_date.asc(), Booking.booking_time.asc())
            )
        )
        .scalars()
        .all()
    )

    total_reviews = len(reviews)
    average_rating = (
        round(sum(r.rating for r in reviews) / total_reviews, 2) if total_reviews else 0.0
    )
    pending_reviews = sum(1 for r in reviews if r.response_status == ResponseStatus.PENDING)

    now_utc = datetime.now(UTC)
    week_ago = now_utc - timedelta(days=7)

    def _as_utc(dt: datetime | None) -> datetime:
        if dt is None:
            return now_utc
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    posts_this_week = sum(1 for p in posts if _as_utc(p.created_at) >= week_ago)
    scheduled_posts = sum(1 for p in posts if p.status == PostStatus.SCHEDULED)
    total_engagement = sum(
        p.engagement_likes + p.engagement_shares + p.engagement_comments for p in posts
    )

    today = date.today()
    upcoming_bookings = sum(
        1 for b in bookings if b.booking_date >= today and b.status != BookingStatus.CANCELLED
    )
    bookings_today = sum(
        1 for b in bookings if b.booking_date == today and b.status != BookingStatus.CANCELLED
    )

    activities: list[ActivityItem] = []
    for r in reviews[:5]:
        body = r.review_text or ""
        activities.append(
            ActivityItem(
                type="review",
                title=f"New {r.rating}★ {r.platform.title()} review from {r.reviewer_name}",
                detail=(body[:110] + "...") if len(body) > 110 else body,
                timestamp=_as_utc(r.created_at),
                status=r.sentiment.value if r.sentiment else "neutral",
            )
        )
    for p in posts[:5]:
        activities.append(
            ActivityItem(
                type="social",
                title=f"{p.platform.value.title()} post ({p.status.value})",
                detail=(p.content[:110] + "...") if len(p.content) > 110 else p.content,
                timestamp=_as_utc(p.published_at or p.scheduled_at or p.created_at),
                status=p.status.value,
            )
        )
    for b in bookings[:5]:
        activities.append(
            ActivityItem(
                type="booking",
                title=f"Booking: {b.customer_name} — {b.service}",
                detail=f"{b.booking_date.isoformat()} at {b.booking_time.strftime('%H:%M')} ({b.duration_minutes}m)",
                timestamp=_as_utc(b.created_at),
                status=b.status.value,
            )
        )

    activities.sort(key=lambda item: item.timestamp, reverse=True)

    return DashboardOverviewResponse(
        business=BusinessResponse.model_validate(business),
        total_reviews=total_reviews,
        average_rating=average_rating,
        pending_reviews=pending_reviews,
        posts_this_week=posts_this_week,
        total_posts=len(posts),
        scheduled_posts=scheduled_posts,
        upcoming_bookings=upcoming_bookings,
        bookings_today=bookings_today,
        total_bookings=len(bookings),
        total_engagement=total_engagement,
        google_profile_status="verified" if business.google_business_id else "not_configured",
        recent_activity=activities[:10],
    )
