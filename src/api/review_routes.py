"""Customer review listing, AI responding, auto-respond, and analytics routes."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.review_agent import ReviewAgent
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.api_schemas import (
    AutoRespondRequest,
    AutoRespondResponse,
    ReviewAnalyticsResponse,
    ReviewRespondRequest,
)
from src.models.review import ResponseStatus, Review, ReviewResponse, Sentiment

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])
review_agent = ReviewAgent()


@router.get("/{business_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    business_id: int,
    sentiment: Sentiment | None = Query(default=None),
    response_status: ResponseStatus | None = Query(default=None),
    platform: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[Review]:
    """List reviews for a business with optional sentiment, response status, and platform filters."""
    await get_business_or_404(db, business_id)
    stmt = select(Review).where(Review.business_id == business_id)
    if sentiment is not None:
        stmt = stmt.where(Review.sentiment == sentiment)
    if response_status is not None:
        stmt = stmt.where(Review.response_status == response_status)
    if platform:
        stmt = stmt.where(Review.platform == platform.lower())
    stmt = stmt.order_by(Review.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{business_id}/reviews/analytics", response_model=ReviewAnalyticsResponse)
async def get_review_analytics(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> ReviewAnalyticsResponse:
    """Compute sentiment breakdown, star distribution, response rate, and trend."""
    await get_business_or_404(db, business_id)
    stmt = select(Review).where(Review.business_id == business_id).order_by(Review.created_at.asc())
    reviews = list((await db.execute(stmt)).scalars().all())

    total = len(reviews)
    if total == 0:
        return ReviewAnalyticsResponse(
            business_id=business_id,
            total_reviews=0,
            average_rating=0.0,
            response_rate=0.0,
            pending_count=0,
            sentiment_breakdown={"positive": 0, "neutral": 0, "negative": 0},
            rating_distribution={"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            platform_breakdown={},
            recent_trend=[],
        )

    avg_rating = round(sum(r.rating for r in reviews) / total, 2)
    responded = sum(1 for r in reviews if r.response_status == ResponseStatus.RESPONDED)
    pending = sum(1 for r in reviews if r.response_status == ResponseStatus.PENDING)
    response_rate = round((responded / total) * 100, 1)

    sentiment_counts = Counter(
        (r.sentiment or review_agent.analyze_sentiment(r.rating, r.review_text)).value
        for r in reviews
    )
    rating_dist = {str(i): 0 for i in range(1, 6)}
    for r in reviews:
        rating_dist[str(max(1, min(5, r.rating)))] += 1

    platform_counts = Counter(r.platform for r in reviews)
    recent_trend = [
        {
            "date": r.created_at.date().isoformat(),
            "rating": r.rating,
            "sentiment": r.sentiment.value if r.sentiment else "neutral",
            "platform": r.platform,
        }
        for r in reviews[-15:]
    ]

    return ReviewAnalyticsResponse(
        business_id=business_id,
        total_reviews=total,
        average_rating=avg_rating,
        response_rate=response_rate,
        pending_count=pending,
        sentiment_breakdown={
            "positive": sentiment_counts.get("positive", 0),
            "neutral": sentiment_counts.get("neutral", 0),
            "negative": sentiment_counts.get("negative", 0),
        },
        rating_distribution=rating_dist,
        platform_breakdown=dict(platform_counts),
        recent_trend=recent_trend,
    )


@router.post("/{business_id}/reviews/auto-respond", response_model=AutoRespondResponse)
async def auto_respond_reviews(
    business_id: int,
    payload: AutoRespondRequest,
    db: AsyncSession = Depends(get_db),
) -> AutoRespondResponse:
    """Auto-respond to pending reviews using AI."""
    business = await get_business_or_404(db, business_id)
    stmt = select(Review).where(
        Review.business_id == business_id,
        Review.response_status == ResponseStatus.PENDING,
        Review.rating >= payload.min_rating,
    )
    if payload.only_positive:
        stmt = stmt.where(Review.rating >= 4)
    stmt = stmt.order_by(Review.created_at.desc()).limit(payload.max_count)

    pending_reviews = list((await db.execute(stmt)).scalars().all())
    now = datetime.now(UTC)
    responded_ids: list[int] = []

    for rev in pending_reviews:
        reply_text = await review_agent.draft_response(
            business=business, review=rev, tone=payload.tone
        )
        rev.response_text = reply_text
        rev.response_status = ResponseStatus.RESPONDED
        rev.responded_at = now
        if rev.sentiment is None:
            rev.sentiment = review_agent.analyze_sentiment(rev.rating, rev.review_text)
        responded_ids.append(rev.id)

    await db.commit()
    return AutoRespondResponse(
        business_id=business_id,
        processed_count=len(responded_ids),
        responded_review_ids=responded_ids,
    )


@router.post("/{business_id}/reviews/{review_id}/respond", response_model=ReviewResponse)
async def respond_to_review(
    business_id: int,
    review_id: int,
    payload: ReviewRespondRequest,
    db: AsyncSession = Depends(get_db),
) -> Review:
    """Respond to a specific customer review (custom text or AI-generated)."""
    business = await get_business_or_404(db, business_id)
    stmt = select(Review).where(
        Review.id == review_id,
        Review.business_id == business_id,
    )
    review = (await db.execute(stmt)).scalar_one_or_none()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found for business {business_id}",
        )

    reply_text = (payload.response_text or "").strip()
    if payload.use_ai or not reply_text:
        reply_text = await review_agent.draft_response(
            business=business, review=review, tone=payload.tone
        )

    review.response_text = reply_text
    review.response_status = ResponseStatus.RESPONDED
    review.responded_at = datetime.now(UTC)
    if review.sentiment is None:
        review.sentiment = review_agent.analyze_sentiment(review.rating, review.review_text)

    await db.commit()
    await db.refresh(review)
    return review
