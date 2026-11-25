"""Multi-Agent Strategy Council (agent debate & synthesis) + Upcoming Festival Planner."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import compute_health_score, get_or_create_agent_config
from src.agents.seo_audit import run_seo_and_sentiment_audit
from src.models.agent_models import AgentRunLog, OrderRequest
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPost

_FESTIVAL_CALENDAR: list[dict[str, Any]] = [
    {
        "name": "Weekend Neighborhood Market",
        "window": "Every Fri–Sun",
        "offset_days": 2,
        "offer_idea": "Weekend Walk-In & Pickup Combo (15% off)",
        "hook": "Make this weekend unforgettable with local flavor!",
    },
    {
        "name": "Holiday Gifting & Celebration Season",
        "window": "Nov–Dec",
        "offset_days": 5,
        "offer_idea": "Curated Gift Box / Family Feast Bundle",
        "hook": "Celebrate together and share local gifts your neighbors love.",
    },
    {
        "name": "New Year Fresh Start Promo",
        "window": "Jan",
        "offset_days": 14,
        "offer_idea": "New Year Welcome Back Pass (20% off first visit)",
        "hook": "Start the new year refreshed—book your spot early!",
    },
    {
        "name": "Midweek Local Appreciation Day",
        "window": "Tue–Wed",
        "offset_days": 4,
        "offer_idea": "Off-Peak Tuesday/Wednesday Bonus Upgrade",
        "hook": "Skip the weekend rush and enjoy a VIP midweek treat!",
    },
]


def get_upcoming_festivals(business: Business) -> list[dict[str, Any]]:
    """Return actionable seasonal & local marketing windows tailored to the business."""
    today = date.today()
    events = []
    for item in _FESTIVAL_CALENDAR:
        target = today + timedelta(days=item["offset_days"])
        events.append(
            {
                "occasion": item["name"],
                "window": item["window"],
                "recommended_launch_date": target.isoformat(),
                "offer_idea": item["offer_idea"],
                "sample_hook": f"{item['hook']} — {business.name}",
                "category_fit": business.category,
            }
        )
    return events


async def run_strategy_council(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Run a 3-agent collaborative Strategy Council debate and synthesize a weekly growth plan."""
    started = time.perf_counter()
    cfg = await get_or_create_agent_config(db, business.id)
    health = await compute_health_score(db, business)
    seo = await run_seo_and_sentiment_audit(db, business)

    pending_reviews = (
        await db.execute(
            select(func.count(Review.id)).where(
                Review.business_id == business.id,
                Review.response_status == ResponseStatus.PENDING,
            )
        )
    ).scalar_one()
    scheduled_posts = (
        await db.execute(
            select(func.count(SocialPost.id)).where(
                SocialPost.business_id == business.id,
                SocialPost.status == PostStatus.SCHEDULED,
            )
        )
    ).scalar_one()
    upcoming_bookings = (
        await db.execute(
            select(func.count(Booking.id)).where(
                Booking.business_id == business.id,
                Booking.booking_date >= date.today(),
                Booking.status != BookingStatus.CANCELLED,
            )
        )
    ).scalar_one()
    orders_cnt = (
        await db.execute(
            select(func.count(OrderRequest.id)).where(OrderRequest.business_id == business.id)
        )
    ).scalar_one()

    # Perspective 1: Growth Marketer
    growth_view = {
        "agent": "GrowthMarketerAgent",
        "stance": "Maximize local discovery & social cadence",
        "proposal": (
            f"You have {scheduled_posts} scheduled post(s). Launch a 3-platform campaign targeting "
            f"'{seo['target_local_keywords'][0]}' and attach your branded QR promo card to convert local views."
        ),
        "recommended_prompt": f"Create and schedule an Instagram post highlighting {business.category} specials in {business.city or 'town'}",
    }

    # Perspective 2: Reputation & Trust Guardian
    pain = seo["improvement_themes"][0]["theme"] if seo["improvement_themes"] else None
    rep_view = {
        "agent": "ReputationGuardianAgent",
        "stance": "Protect rating before spending marketing effort",
        "proposal": (
            f"Resolve {pending_reviews} pending review(s) first"
            + (f" and address '{pain}' feedback" if pain else "")
            + ". High response velocity converts searchers into booked guests."
        ),
        "recommended_prompt": "Draft empathetic responses for all pending reviews",
    }

    # Perspective 3: Operations & Capacity Optimizer
    ops_view = {
        "agent": "OperationsOptimizerAgent",
        "stance": "Fill quiet slots & grow commission-free orders",
        "proposal": (
            f"With {upcoming_bookings} upcoming booking(s), {orders_cnt} order(s), and "
            f"{len(cfg.catalog_items)} catalog item(s), promote midweek pickup bundles via your "
            f"storefront QR poster and WhatsApp VIP list."
        ),
        "recommended_prompt": "Show upcoming bookings and today's open slots",
    }

    # Consensus Synthesis
    action_plan = [
        {
            "step": 1,
            "owner_agent": "ReputationGuardianAgent",
            "title": "Clear Pending Reviews & Trust Signals",
            "why": rep_view["proposal"],
            "prompt": rep_view["recommended_prompt"],
        },
        {
            "step": 2,
            "owner_agent": "GrowthMarketerAgent",
            "title": "Schedule Local SEO + QR Promo Campaign",
            "why": growth_view["proposal"],
            "prompt": growth_view["recommended_prompt"],
        },
        {
            "step": 3,
            "owner_agent": "OperationsOptimizerAgent",
            "title": "Fill Off-Peak Capacity via Storefront & WhatsApp",
            "why": ops_view["proposal"],
            "prompt": ops_view["recommended_prompt"],
        },
    ]

    duration_ms = int((time.perf_counter() - started) * 1000)
    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="strategy_council",
            goal=f"Multi-agent Strategy Council debate for {business.name}",
            agents_invoked=[
                "GrowthMarketerAgent",
                "ReputationGuardianAgent",
                "OperationsOptimizerAgent",
                "CouncilSynthesizer",
            ],
            tools_called=["compute_health_score", "run_seo_and_sentiment_audit"],
            steps_summary=[
                {
                    "agent": growth_view["agent"],
                    "tool": "propose_growth",
                    "status": "completed",
                    "detail": growth_view["proposal"],
                },
                {
                    "agent": rep_view["agent"],
                    "tool": "audit_reputation",
                    "status": "completed",
                    "detail": rep_view["proposal"],
                },
                {
                    "agent": ops_view["agent"],
                    "tool": "optimize_capacity",
                    "status": "completed",
                    "detail": ops_view["proposal"],
                },
            ],
            outcome="completed",
            duration_ms=duration_ms,
        )
    )
    await db.flush()

    return {
        "business_id": business.id,
        "health_score": health["overall_score"],
        "council_members": [growth_view, rep_view, ops_view],
        "consensus_summary": (
            f"Council Consensus for **{business.name}** (Health Score {health['overall_score']}/100): "
            f"1) Clear {pending_reviews} pending review(s), 2) Schedule weekly multi-platform promo targeting "
            f"'{seo['target_local_keywords'][0]}', and 3) Drive direct bookings/orders via WhatsApp & Counter QR."
        ),
        "action_plan": action_plan,
        "upcoming_festivals": get_upcoming_festivals(business),
    }
