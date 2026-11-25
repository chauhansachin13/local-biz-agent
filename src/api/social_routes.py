"""Social media posting, scheduling, content calendar, and AI generation routes."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.social_agent import SocialMediaAgent
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.api_schemas import (
    ContentCalendarDay,
    ContentCalendarResponse,
    GenerateContentRequest,
    GenerateContentResponse,
    SocialPostCreateRequest,
    SocialPostScheduleRequest,
)
from src.models.social_post import (
    PostStatus,
    SocialPlatform,
    SocialPost,
    SocialPostResponse,
)

router = APIRouter(prefix="/api/social", tags=["Social Media"])
social_agent = SocialMediaAgent()


@router.post(
    "/{business_id}/post",
    response_model=SocialPostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_social_post(
    business_id: int,
    payload: SocialPostCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> SocialPost:
    """Create and publish (or save as draft) a social media post."""
    await get_business_or_404(db, business_id)
    now = datetime.now(timezone.utc)
    post_status = (
        PostStatus.DRAFT if payload.status.lower() == "draft" else PostStatus.PUBLISHED
    )
    post = SocialPost(
        business_id=business_id,
        platform=payload.platform,
        content=payload.content,
        image_url=payload.image_url,
        status=post_status,
        published_at=now if post_status == PostStatus.PUBLISHED else None,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.post(
    "/{business_id}/schedule",
    response_model=SocialPostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_social_post(
    business_id: int,
    payload: SocialPostScheduleRequest,
    db: AsyncSession = Depends(get_db),
) -> SocialPost:
    """Schedule a social media post for future publication."""
    await get_business_or_404(db, business_id)
    post = SocialPost(
        business_id=business_id,
        platform=payload.platform,
        content=payload.content,
        image_url=payload.image_url,
        status=PostStatus.SCHEDULED,
        scheduled_at=payload.scheduled_at,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.get("/{business_id}/posts", response_model=list[SocialPostResponse])
async def list_social_posts(
    business_id: int,
    platform: SocialPlatform | None = Query(default=None),
    post_status: PostStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[SocialPost]:
    """List social posts for a business with optional platform and status filters."""
    await get_business_or_404(db, business_id)
    stmt = select(SocialPost).where(SocialPost.business_id == business_id)
    if platform is not None:
        stmt = stmt.where(SocialPost.platform == platform)
    if post_status is not None:
        stmt = stmt.where(SocialPost.status == post_status)
    stmt = stmt.order_by(SocialPost.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{business_id}/calendar", response_model=ContentCalendarResponse)
async def get_content_calendar(
    business_id: int,
    days: int = Query(default=14, ge=1, le=90),
    start_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ContentCalendarResponse:
    """Return a day-by-day content calendar of scheduled and published posts."""
    await get_business_or_404(db, business_id)
    start = start_date or (date.today() - timedelta(days=3))
    end = start + timedelta(days=days - 1)

    stmt = (
        select(SocialPost)
        .where(SocialPost.business_id == business_id)
        .order_by(SocialPost.scheduled_at.asc(), SocialPost.created_at.asc())
    )
    posts = list((await db.execute(stmt)).scalars().all())

    grouped: dict[str, list[SocialPostResponse]] = defaultdict(list)
    total_in_window = 0
    for post in posts:
        ref_dt = post.scheduled_at or post.published_at or post.created_at
        post_day = ref_dt.date()
        if start <= post_day <= end:
            grouped[post_day.isoformat()].append(SocialPostResponse.model_validate(post))
            total_in_window += 1

    calendar_days = [
        ContentCalendarDay(
            date=(start + timedelta(days=offset)).isoformat(),
            posts=grouped.get((start + timedelta(days=offset)).isoformat(), []),
        )
        for offset in range(days)
    ]

    return ContentCalendarResponse(
        business_id=business_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        total_posts=total_in_window,
        days=calendar_days,
    )


@router.post("/{business_id}/generate-content", response_model=GenerateContentResponse)
async def generate_social_content(
    business_id: int,
    payload: GenerateContentRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateContentResponse:
    """Use AI to generate platform-tailored social post content and hashtags."""
    business = await get_business_or_404(db, business_id)
    result = await social_agent.generate_post(
        business=business,
        platform=payload.platform.value,
        topic=payload.topic,
        tone=payload.tone,
        include_hashtags=payload.include_hashtags,
        call_to_action=payload.call_to_action,
    )
    return GenerateContentResponse(**result)
