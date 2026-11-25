"""Customer CRM syncing, Loyalty Retention Agent, and Competitor Benchmarking Agent."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_models import (
    AgentApprovalAction,
    AgentRunLog,
    ApprovalStatus,
    CompetitorBenchmark,
    CustomerProfile,
    OrderRequest,
    RiskLevel,
)
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import Review


def _classify_segment(visits: int, spent: float) -> str:
    if visits >= 3 or spent >= 100.0:
        return "VIP"
    if visits == 2 or spent >= 40.0:
        return "Regular"
    return "New"


async def sync_customers_from_activity(db: AsyncSession, business_id: int) -> list[CustomerProfile]:
    """Build or update unified CustomerProfile rows from bookings, orders, and reviews."""
    existing = list(
        (
            await db.execute(
                select(CustomerProfile).where(CustomerProfile.business_id == business_id)
            )
        )
        .scalars()
        .all()
    )
    by_key: dict[str, CustomerProfile] = {}
    for cust in existing:
        key = (cust.phone or cust.email or cust.name).strip().lower()
        by_key[key] = cust

    bookings = list(
        (
            await db.execute(
                select(Booking).where(
                    Booking.business_id == business_id,
                    Booking.status != BookingStatus.CANCELLED,
                )
            )
        )
        .scalars()
        .all()
    )
    orders = list(
        (await db.execute(select(OrderRequest).where(OrderRequest.business_id == business_id)))
        .scalars()
        .all()
    )
    reviews = list(
        (await db.execute(select(Review).where(Review.business_id == business_id))).scalars().all()
    )

    agg: dict[str, dict[str, Any]] = {}

    def _accumulate(
        name: str, phone: str | None, email: str | None, spent: float, dt: datetime | None
    ):
        clean_key = (phone or email or name).strip().lower()
        if not clean_key:
            return
        entry = agg.setdefault(
            clean_key,
            {
                "name": name,
                "phone": phone,
                "email": email,
                "visits": 0,
                "spent": 0.0,
                "last": dt or datetime.now(UTC),
            },
        )
        entry["visits"] += 1
        entry["spent"] += spent
        if phone and not entry["phone"]:
            entry["phone"] = phone
        if email and not entry["email"]:
            entry["email"] = email

    for b in bookings:
        _accumulate(b.customer_name, b.customer_phone, b.customer_email, 35.0, b.created_at)
    for o in orders:
        _accumulate(
            o.customer_name, o.customer_phone, o.customer_email, float(o.total_amount), o.created_at
        )
    for r in reviews:
        _accumulate(r.reviewer_name, None, None, 0.0, r.created_at)

    now = datetime.now(UTC)
    for key, info in agg.items():
        if key in by_key:
            cust = by_key[key]
            cust.visit_count = max(cust.visit_count, info["visits"])
            cust.total_spent = max(cust.total_spent, round(info["spent"], 2))
            cust.loyalty_points = cust.visit_count * 15 + int(cust.total_spent)
            cust.segment = _classify_segment(cust.visit_count, cust.total_spent)
        else:
            cust = CustomerProfile(
                business_id=business_id,
                name=info["name"],
                phone=info["phone"],
                email=info["email"],
                visit_count=info["visits"],
                total_spent=round(info["spent"], 2),
                loyalty_points=info["visits"] * 15 + int(info["spent"]),
                segment=_classify_segment(info["visits"], info["spent"]),
                last_visit_at=info["last"] or now,
            )
            db.add(cust)
            by_key[key] = cust

    await db.flush()
    return list(
        (
            await db.execute(
                select(CustomerProfile)
                .where(CustomerProfile.business_id == business_id)
                .order_by(CustomerProfile.total_spent.desc(), CustomerProfile.visit_count.desc())
            )
        )
        .scalars()
        .all()
    )


async def draft_retention_campaigns(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Identify VIP & New/At-Risk customers and queue personalized loyalty outreach in HITL Inbox."""
    started = time.perf_counter()
    customers = await sync_customers_from_activity(db, business.id)
    queued: list[dict[str, Any]] = []

    for cust in customers[:5]:
        if cust.segment == "VIP":
            msg = (
                f"Hi {cust.name.split()[0]}! 🌟 As a VIP at {business.name} "
                f"({cust.loyalty_points} loyalty pts), enjoy a complimentary upgrade or 20% off "
                "your next visit this week!"
            )
            title = f"VIP Loyalty Thank-You to {cust.name}"
        else:
            msg = (
                f"Hi {cust.name.split()[0]}! We'd love to welcome you back to {business.name}. "
                "Show this message or book via our page for 15% off your next visit!"
            )
            title = f"Retention Offer to {cust.name} ({cust.segment})"

        action = AgentApprovalAction(
            business_id=business.id,
            action_type="send_loyalty_offer",
            title=title,
            description=f"Target: {cust.phone or cust.email or cust.name} • Segment: {cust.segment}",
            agent_name="LoyaltyRetentionAgent",
            reasoning=f"Customer has {cust.visit_count} visit(s) and ${cust.total_spent:.2f} spend; personalized retention outreach boosts repeat visits.",
            risk_level=RiskLevel.LOW,
            payload={
                "customer_id": cust.id,
                "customer_name": cust.name,
                "phone": cust.phone,
                "content": msg,
            },
            status=ApprovalStatus.PENDING,
        )
        db.add(action)
        await db.flush()
        queued.append(
            {
                "approval_id": action.id,
                "customer": cust.name,
                "segment": cust.segment,
                "message": msg,
            }
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="loyalty_retention",
            goal=f"Drafted {len(queued)} personalized loyalty/retention offers",
            agents_invoked=["LoyaltyRetentionAgent"],
            tools_called=["sync_customers_from_activity", "queue_loyalty_offer"],
            steps_summary=[
                {
                    "agent": "LoyaltyRetentionAgent",
                    "tool": "draft_retention_campaigns",
                    "status": "awaiting_approval",
                    "detail": f"Queued {len(queued)} customer offer(s) in Approval Inbox.",
                }
            ],
            outcome="awaiting_approval",
            duration_ms=duration_ms,
        )
    )
    await db.flush()
    return {"business_id": business.id, "queued_count": len(queued), "offers": queued}


async def analyze_competitors(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Compare business ratings and offerings against tracked local competitors."""
    competitors = list(
        (
            await db.execute(
                select(CompetitorBenchmark).where(CompetitorBenchmark.business_id == business.id)
            )
        )
        .scalars()
        .all()
    )
    reviews = list(
        (await db.execute(select(Review).where(Review.business_id == business.id))).scalars().all()
    )
    own_rating = round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 4.5
    own_reviews = len(reviews)

    comparisons: list[dict[str, Any]] = []
    counter_moves: list[str] = []

    for comp in competitors:
        rating_gap = round(own_rating - comp.rating, 2)
        comparisons.append(
            {
                "id": comp.id,
                "name": comp.name,
                "rating": comp.rating,
                "review_count": comp.review_count,
                "price_tier": comp.price_tier,
                "rating_advantage": rating_gap,
                "strengths": comp.strengths,
                "weaknesses": comp.weaknesses,
            }
        )
        if comp.weaknesses:
            counter_moves.append(
                f"Differentiate from {comp.name} (weakness: '{comp.weaknesses}') by spotlighting your fast booking/pickup guarantee."
            )
        if comp.review_count > own_reviews:
            counter_moves.append(
                f"{comp.name} has {comp.review_count} reviews vs your {own_reviews}. Put your Counter QR Poster at checkout to ask happy guests for reviews!"
            )

    if not competitors:
        counter_moves.append(
            "Add 1–2 nearby competitors to generate tailored counter-positioning campaigns."
        )

    return {
        "business_id": business.id,
        "own_rating": own_rating,
        "own_review_count": own_reviews,
        "competitors": comparisons,
        "recommended_counter_strategies": counter_moves,
    }
