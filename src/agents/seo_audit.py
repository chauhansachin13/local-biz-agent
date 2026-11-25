"""Local SEO audit, review theme extraction, and Morning Executive Daily Brief agent."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import compute_health_score, get_or_create_agent_config
from src.models.agent_models import (
    AgentApprovalAction,
    ApprovalStatus,
    OrderRequest,
    OrderStatus,
)
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review, Sentiment

_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Food / Product Quality": (
        "pizza",
        "pasta",
        "delicious",
        "fresh",
        "tiramisu",
        "balayage",
        "haircut",
        "coffee",
        "quality",
    ),
    "Staff & Hospitality": (
        "staff",
        "friendly",
        "attentive",
        "server",
        "stylist",
        "helpful",
        "polite",
        "team",
    ),
    "Ambiance & Cleanliness": ("cozy", "ambiance", "clean", "relaxing", "atmosphere", "noise"),
    "Wait Times & Pacing": ("wait", "waited", "late", "minutes", "rushed", "slow", "disorganized"),
    "Pricing & Value": ("price", "pricey", "expensive", "worth", "fair"),
}


async def run_seo_and_sentiment_audit(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Audit local SEO completeness, target keywords, and customer review themes."""
    cfg = await get_or_create_agent_config(db, business.id)
    reviews = list(
        (await db.execute(select(Review).where(Review.business_id == business.id))).scalars().all()
    )
    health = await compute_health_score(db, business)

    praised: Counter[str] = Counter()
    pain_points: Counter[str] = Counter()

    for rev in reviews:
        low = (rev.review_text or "").lower()
        tokens = set(re.findall(r"[a-z]+", low))
        for theme, kws in _THEME_KEYWORDS.items():
            if tokens & set(kws):
                if rev.rating >= 4 or rev.sentiment == Sentiment.POSITIVE:
                    praised[theme] += 1
                elif rev.rating <= 3 or rev.sentiment == Sentiment.NEGATIVE:
                    pain_points[theme] += 1

    city = business.city or "near me"
    cat = business.category.lower()
    keywords = [
        f"best {cat} in {city}",
        f"{cat} near {city}",
        f"{business.name} {city}",
        f"book {cat} online {city}",
        f"top rated {cat} {business.state or city}".strip(),
    ]

    nap_checks = [
        {"field": "Business Name", "ok": bool(business.name), "value": business.name},
        {
            "field": "Full Address",
            "ok": bool(business.address and business.city),
            "value": f"{business.address or ''} {business.city or ''}".strip(),
        },
        {"field": "Phone Number", "ok": bool(business.phone), "value": business.phone or "Missing"},
        {
            "field": "Google Business ID",
            "ok": bool(business.google_business_id),
            "value": business.google_business_id or "Not Linked",
        },
        {
            "field": "Operating Hours",
            "ok": bool(business.operating_hours),
            "value": "Configured" if business.operating_hours else "Missing",
        },
        {
            "field": "Service Catalog",
            "ok": len(cfg.catalog_items) > 0,
            "value": f"{len(cfg.catalog_items)} item(s)",
        },
    ]
    nap_score = int((sum(1 for c in nap_checks if c["ok"]) / len(nap_checks)) * 100)

    recommendations = []
    if pain_points:
        top_issue, cnt = pain_points.most_common(1)[0]
        recommendations.append(
            f"Address '{top_issue}' mentioned in {cnt} review(s) and highlight fixes in your next GBP update."
        )
    if not business.google_business_id:
        recommendations.append(
            "Verify your Google Business Profile ID to unlock Maps local-pack ranking."
        )
    if len(business.description or "") < 80:
        recommendations.append(
            f"Expand your business description to include '{keywords[0]}' and '{keywords[3]}'."
        )
    if not recommendations:
        recommendations.append(
            f"Maintain weekly posts targeting '{keywords[0]}' and keep reply rate above 90%."
        )

    return {
        "business_id": business.id,
        "health_score": health["overall_score"],
        "nap_consistency_score": nap_score,
        "nap_checks": nap_checks,
        "target_local_keywords": keywords,
        "top_strengths": [{"theme": k, "mentions": v} for k, v in praised.most_common(4)],
        "improvement_themes": [{"theme": k, "mentions": v} for k, v in pain_points.most_common(4)],
        "recommendations": recommendations,
    }


async def generate_daily_brief(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Generate a concise Morning Executive Briefing for the business owner."""
    today = date.today()
    bookings_today = (
        await db.execute(
            select(func.count(Booking.id)).where(
                Booking.business_id == business.id,
                Booking.booking_date == today,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
    ).scalar_one()
    active_orders = (
        await db.execute(
            select(func.count(OrderRequest.id)).where(
                OrderRequest.business_id == business.id,
                OrderRequest.status.not_in([OrderStatus.COMPLETED, OrderStatus.CANCELLED]),
            )
        )
    ).scalar_one()
    pending_reviews = (
        await db.execute(
            select(func.count(Review.id)).where(
                Review.business_id == business.id,
                Review.response_status == ResponseStatus.PENDING,
            )
        )
    ).scalar_one()
    pending_approvals = (
        await db.execute(
            select(func.count(AgentApprovalAction.id)).where(
                AgentApprovalAction.business_id == business.id,
                AgentApprovalAction.status == ApprovalStatus.PENDING,
            )
        )
    ).scalar_one()

    health = await compute_health_score(db, business)

    if pending_approvals > 0:
        top_action = f"Review {pending_approvals} pending AI draft(s) in your Approval Inbox."
    elif pending_reviews > 0:
        top_action = f"Respond to {pending_reviews} pending customer review(s)."
    elif active_orders > 0:
        top_action = f"Fulfill {active_orders} active online order(s)."
    else:
        top_action = health["top_recommendation"]

    summary = (
        f"Good morning, **{business.name}**! Today ({today.isoformat()}): "
        f"**{bookings_today}** booking(s), **{active_orders}** active order(s), "
        f"**{pending_reviews}** pending review(s), and **{pending_approvals}** HITL approval(s). "
        f"Digital Health Score: **{health['overall_score']}/100 ({health['grade']})**."
    )

    return {
        "business_id": business.id,
        "date": today.isoformat(),
        "summary": summary,
        "metrics": {
            "bookings_today": bookings_today,
            "active_orders": active_orders,
            "pending_reviews": pending_reviews,
            "pending_approvals": pending_approvals,
            "health_score": health["overall_score"],
            "grade": health["grade"],
        },
        "priority_action": top_action,
    }
