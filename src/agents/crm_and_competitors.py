"""Customer CRM syncing, Loyalty Retention Agent, and Competitor Benchmarking Agent."""

from __future__ import annotations

import asyncio
import re
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


def _norm_phone(phone: str | None) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    return f"tel:{digits[-10:]}" if len(digits) >= 7 else ""


def _norm_email(email: str | None) -> str:
    clean = (email or "").strip().lower()
    return f"mail:{clean}" if clean else ""


def _norm_name(name: str | None) -> str:
    clean = re.sub(r"\s+", " ", (name or "").strip().lower())
    return f"name:{clean}" if clean else ""


def _identity_keys(name: str | None, phone: str | None, email: str | None) -> list[str]:
    return [k for k in (_norm_phone(phone), _norm_email(email), _norm_name(name)) if k]


_CRM_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}


def _get_crm_lock(business_id: int) -> asyncio.Lock:
    loop_id = id(asyncio.get_running_loop())
    key = (loop_id, business_id)
    lock = _CRM_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _CRM_LOCKS[key] = lock
    return lock


async def sync_customers_from_activity(db: AsyncSession, business_id: int) -> list[CustomerProfile]:
    """Build or update unified CustomerProfile rows from bookings, orders, and reviews safely under concurrency."""
    async with _get_crm_lock(business_id):
        existing = list(
            (
                await db.execute(
                    select(CustomerProfile)
                    .where(CustomerProfile.business_id == business_id)
                    .order_by(CustomerProfile.id.asc())
                )
            )
            .scalars()
            .all()
        )
        existing_index: dict[str, CustomerProfile] = {}
        for cust in existing:
            keys = _identity_keys(cust.name, cust.phone, cust.email)
            primary = next((existing_index[k] for k in keys if k in existing_index), None)
            if primary is not None and primary is not cust:
                primary.visit_count = max(primary.visit_count, cust.visit_count)
                primary.total_spent = max(primary.total_spent, cust.total_spent)
                primary.loyalty_points = max(primary.loyalty_points, cust.loyalty_points)
                if cust.phone and not primary.phone:
                    primary.phone = cust.phone
                if cust.email and not primary.email:
                    primary.email = cust.email
                primary.segment = _classify_segment(primary.visit_count, primary.total_spent)
                await db.delete(cust)
                target = primary
            else:
                target = cust
            for k in keys:
                existing_index[k] = target

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
            (await db.execute(select(Review).where(Review.business_id == business_id)))
            .scalars()
            .all()
        )

        records: list[dict[str, Any]] = []
        agg_index: dict[str, dict[str, Any]] = {}

        def _accumulate(
            name: str, phone: str | None, email: str | None, spent: float, dt: datetime | None
        ) -> None:
            keys = _identity_keys(name, phone, email)
            if not keys:
                return
            entry = next((agg_index[k] for k in keys if k in agg_index), None)
            if entry is None:
                entry = {
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "visits": 0,
                    "spent": 0.0,
                    "last": dt or datetime.now(UTC),
                    "keys": list(keys),
                }
                records.append(entry)
            else:
                for k in keys:
                    if k not in entry["keys"]:
                        entry["keys"].append(k)
            for k in keys:
                agg_index[k] = entry

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
                o.customer_name,
                o.customer_phone,
                o.customer_email,
                float(o.total_amount),
                o.created_at,
            )
        for r in reviews:
            _accumulate(r.reviewer_name, None, None, 0.0, r.created_at)

        now = datetime.now(UTC)
        for info in records:
            cust = next((existing_index[k] for k in info["keys"] if k in existing_index), None)
            if cust is not None:
                cust.visit_count = max(cust.visit_count, info["visits"])
                cust.total_spent = max(cust.total_spent, round(info["spent"], 2))
                cust.loyalty_points = cust.visit_count * 15 + int(cust.total_spent)
                cust.segment = _classify_segment(cust.visit_count, cust.total_spent)
                if info["phone"] and not cust.phone:
                    cust.phone = info["phone"]
                if info["email"] and not cust.email:
                    cust.email = info["email"]
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
            for k in info["keys"]:
                existing_index[k] = cust

        await db.commit()
        return list(
            (
                await db.execute(
                    select(CustomerProfile)
                    .where(CustomerProfile.business_id == business_id)
                    .order_by(
                        CustomerProfile.total_spent.desc(), CustomerProfile.visit_count.desc()
                    )
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
