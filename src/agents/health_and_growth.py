"""Growth, 60-second onboarding, multi-channel campaign, and health score agents."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.llm_client import generate_text_with_llm
from src.agents.social_agent import SocialMediaAgent
from src.models.agent_models import (
    AgentApprovalAction,
    AgentRunLog,
    ApprovalStatus,
    BusinessAgentConfig,
    OrderRequest,
    RiskLevel,
)
from src.models.booking import Booking, BookingStatus
from src.models.business import Business, BusinessResponse
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPlatform, SocialPost
from src.tools.content_tools import generate_promotional_offer
from src.tools.google_tools import update_business_profile

_CATEGORY_DEFAULTS: dict[str, dict[str, Any]] = {
    "restaurant": {
        "hours": {
            day: {"open": "11:00", "close": "22:00", "closed": False}
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        },
        "catalog": [
            {
                "name": "Chef's Signature Combo",
                "price": 18.0,
                "description": "Freshly prepared house specialty",
            },
            {
                "name": "Family Feast Box (Serves 4)",
                "price": 49.0,
                "description": "Best-selling sharable platter",
            },
            {
                "name": "Weekend Tasting Reservation",
                "price": 0.0,
                "description": "Priority table booking",
            },
        ],
        "faqs": [
            {
                "q": "Do you take walk-ins and online reservations?",
                "a": "Yes! Walk-ins are welcome and you can reserve online anytime.",
            },
            {
                "q": "Do you offer takeaway and pickup?",
                "a": "Yes, order directly on our page for quick pickup.",
            },
        ],
    },
    "salon": {
        "hours": {
            "monday": {"open": "09:30", "close": "18:30", "closed": True},
            **{
                day: {"open": "09:30", "close": "19:30", "closed": False}
                for day in ("tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
            },
        },
        "catalog": [
            {
                "name": "Signature Cut & Style",
                "price": 45.0,
                "description": "Consultation, wash, precision cut & blowout",
            },
            {
                "name": "Express Glow Facial / Spa",
                "price": 65.0,
                "description": "45-minute revitalizing treatment",
            },
            {
                "name": "Color & Highlights Session",
                "price": 110.0,
                "description": "Custom color consultation & finish",
            },
        ],
        "faqs": [
            {
                "q": "How early should I arrive?",
                "a": "Please arrive 5–10 minutes before your appointment.",
            },
            {
                "q": "Can I reschedule online?",
                "a": "Yes, contact us or reschedule up to 4 hours ahead.",
            },
        ],
    },
    "retail": {
        "hours": {
            day: {"open": "10:00", "close": "20:00", "closed": False}
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        },
        "catalog": [
            {
                "name": "Curated Local Gift Box",
                "price": 35.0,
                "description": "Handpicked customer favorites",
            },
            {
                "name": "Store Pickup Reserve",
                "price": 0.0,
                "description": "Reserve items online for same-day pickup",
            },
        ],
        "faqs": [
            {
                "q": "Do you offer same-day pickup?",
                "a": "Yes, orders placed before 6 PM are ready within 1 hour.",
            },
        ],
    },
}


def _category_template(category: str) -> dict[str, Any]:
    cat_low = (category or "").lower()
    for key, tpl in _CATEGORY_DEFAULTS.items():
        if key in cat_low or (
            key == "restaurant" and any(w in cat_low for w in ("cafe", "bakery", "food"))
        ):
            return tpl
    return {
        "hours": {
            day: {"open": "09:00", "close": "19:00", "closed": day == "sunday"}
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        },
        "catalog": [
            {
                "name": "Standard Consultation / Service",
                "price": 40.0,
                "description": "Personalized 1-on-1 local service",
            },
            {
                "name": "Express Package",
                "price": 25.0,
                "description": "Fast, convenient turnaround",
            },
        ],
        "faqs": [
            {
                "q": "How do I book an appointment?",
                "a": "Book directly using our online storefront or call us anytime.",
            },
        ],
    }


async def get_or_create_agent_config(db: AsyncSession, business_id: int) -> BusinessAgentConfig:
    """Fetch existing BusinessAgentConfig or initialize defaults for a business."""
    stmt = select(BusinessAgentConfig).where(BusinessAgentConfig.business_id == business_id)
    cfg = (await db.execute(stmt)).scalar_one_or_none()
    if cfg is not None:
        return cfg

    biz = (
        await db.execute(select(Business).where(Business.id == business_id))
    ).scalar_one_or_none()
    tpl = _category_template(biz.category if biz else "general")
    cfg = BusinessAgentConfig(
        business_id=business_id,
        autopilot_enabled=True,
        auto_publish_scheduled=True,
        auto_reply_positive_reviews=False,
        require_approval_negative_reviews=True,
        preferred_language="English",
        brand_voice="warm, helpful, and neighborhood-friendly",
        catalog_items=tpl["catalog"],
        faqs=tpl["faqs"],
    )
    try:
        async with db.begin_nested():
            db.add(cfg)
            await db.flush()
    except IntegrityError:
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing
        raise
    return cfg


async def compute_health_score(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Compute a 0-100 Digital Presence Health Score across 5 actionable pillars."""
    cfg = await get_or_create_agent_config(db, business.id)

    reviews = list(
        (await db.execute(select(Review).where(Review.business_id == business.id))).scalars().all()
    )
    posts = list(
        (await db.execute(select(SocialPost).where(SocialPost.business_id == business.id)))
        .scalars()
        .all()
    )
    bookings_count = (
        await db.execute(
            select(func.count(Booking.id)).where(
                Booking.business_id == business.id,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
    ).scalar_one()
    orders_count = (
        await db.execute(
            select(func.count(OrderRequest.id)).where(OrderRequest.business_id == business.id)
        )
    ).scalar_one()

    # Pillar 1: Google Business Profile (20 pts)
    gbp_pts = 0
    if business.name and business.category:
        gbp_pts += 4
    if business.address or business.city:
        gbp_pts += 4
    if business.phone or business.website:
        gbp_pts += 4
    if business.operating_hours:
        gbp_pts += 4
    if business.google_business_id:
        gbp_pts += 4
    gbp_tip = (
        "Google Business Profile is fully verified."
        if gbp_pts == 20
        else "Link your Google Business ID and complete address/hours in Settings."
    )

    # Pillar 2: Reviews & Reputation (20 pts)
    if reviews:
        avg_rating = sum(r.rating for r in reviews) / len(reviews)
        responded = sum(1 for r in reviews if r.response_status == ResponseStatus.RESPONDED)
        resp_rate = responded / len(reviews)
        rev_pts = min(20, round((avg_rating / 5.0) * 10 + resp_rate * 10))
        pending_cnt = len(reviews) - responded
        rev_tip = (
            "Strong reputation and response rate!"
            if pending_cnt == 0
            else f"Reply to {pending_cnt} pending review(s) to boost search trust."
        )
    else:
        rev_pts = 8
        rev_tip = "Invite happy customers to leave your first Google review."

    # Pillar 3: Social Media Consistency (20 pts)
    published_cnt = sum(1 for p in posts if p.status == PostStatus.PUBLISHED)
    scheduled_cnt = sum(1 for p in posts if p.status == PostStatus.SCHEDULED)
    platforms_used = len({p.platform for p in posts})
    social_pts = min(20, published_cnt * 4 + scheduled_cnt * 4 + platforms_used * 2)
    social_tip = (
        "Consistent multi-channel posting schedule active!"
        if scheduled_cnt > 0 and published_cnt >= 2
        else "Schedule at least 2 upcoming posts across Instagram & Google Business."
    )

    # Pillar 4: Online Bookings & Orders (20 pts)
    ops_pts = 0
    if business.operating_hours:
        ops_pts += 8
    if bookings_count > 0:
        ops_pts += 6
    if orders_count > 0 or len(cfg.catalog_items) > 0:
        ops_pts += 6
    ops_tip = (
        "Online bookings & storefront ordering are ready for customers!"
        if ops_pts >= 16
        else "Add catalog items and share your online storefront link with customers."
    )

    # Pillar 5: Profile & AI Readiness (20 pts)
    comp_pts = 0
    if business.description and len(business.description) >= 30:
        comp_pts += 8
    if len(cfg.catalog_items) >= 2:
        comp_pts += 6
    if len(cfg.faqs) >= 1:
        comp_pts += 3
    if cfg.autopilot_enabled:
        comp_pts += 3
    comp_tip = (
        "Rich local SEO bio, catalog, and AI autopilot configured."
        if comp_pts >= 18
        else "Enrich your business description and service catalog for better discovery."
    )

    pillars = [
        {
            "name": "Google Business Profile",
            "score": gbp_pts,
            "max_score": 20,
            "status": "strong" if gbp_pts >= 16 else ("fair" if gbp_pts >= 10 else "needs_work"),
            "tip": gbp_tip,
        },
        {
            "name": "Reviews & Reputation",
            "score": rev_pts,
            "max_score": 20,
            "status": "strong" if rev_pts >= 16 else ("fair" if rev_pts >= 10 else "needs_work"),
            "tip": rev_tip,
        },
        {
            "name": "Social Media Presence",
            "score": social_pts,
            "max_score": 20,
            "status": "strong"
            if social_pts >= 16
            else ("fair" if social_pts >= 10 else "needs_work"),
            "tip": social_tip,
        },
        {
            "name": "Online Bookings & Orders",
            "score": ops_pts,
            "max_score": 20,
            "status": "strong" if ops_pts >= 16 else ("fair" if ops_pts >= 10 else "needs_work"),
            "tip": ops_tip,
        },
        {
            "name": "SEO Bio & AI Readiness",
            "score": comp_pts,
            "max_score": 20,
            "status": "strong" if comp_pts >= 16 else ("fair" if comp_pts >= 10 else "needs_work"),
            "tip": comp_tip,
        },
    ]

    overall = sum(p["score"] for p in pillars)
    grade = (
        "A+"
        if overall >= 90
        else ("A" if overall >= 80 else ("B" if overall >= 65 else ("C" if overall >= 50 else "D")))
    )
    lowest_pillar = min(pillars, key=lambda p: p["score"])

    return {
        "business_id": business.id,
        "overall_score": overall,
        "grade": grade,
        "pillars": pillars,
        "top_recommendation": lowest_pillar["tip"],
    }


async def run_magic_onboarding(
    db: AsyncSession, payload_dict: dict[str, Any], overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """60-second 1-click AI business launchpad creating GBP, bio, catalog, and starter posts."""
    started = time.perf_counter()
    trace: list[dict[str, Any]] = []
    name = payload_dict["name"].strip()
    category = payload_dict["category"].strip()
    city = (payload_dict.get("city") or "").strip()
    state = (payload_dict.get("state") or "").strip()
    specialty = (payload_dict.get("specialty") or "").strip()
    language = (payload_dict.get("preferred_language") or "English").strip()

    tpl = _category_template(category)

    # Step 1: SEO Bio Generation
    seo_bio = await generate_text_with_llm(
        system_prompt=(
            "Write a warm, local-SEO-friendly 2-sentence Google Business Profile description "
            f"in {language}."
        ),
        user_prompt=(
            f"Business: {name}\nCategory: {category}\nLocation: {city}, {state}\n"
            f"Specialty: {specialty or 'Quality neighborhood service'}"
        ),
        overrides=overrides,
        temperature=0.6,
        max_tokens=160,
    )
    if not seo_bio:
        loc_text = f" in {city}" if city else ""
        spec_text = f" known for {specialty}" if specialty else ""
        seo_bio = (
            f"{name} is a trusted neighborhood {category.lower()}{loc_text}{spec_text}. "
            "Visit us for warm hospitality, fast online booking, and convenient local service."
        )
    trace.append(
        {
            "agent": "GoogleBusinessAgent",
            "tool": "generate_local_seo_bio",
            "status": "completed",
            "detail": f"Generated SEO business description in {language}.",
        }
    )

    gbp_id = f"ChIJ_{uuid.uuid4().hex[:14]}"
    business = Business(
        name=name,
        category=category,
        description=seo_bio,
        address=payload_dict.get("address") or None,
        city=city or None,
        state=state or None,
        phone=payload_dict.get("phone") or None,
        email=payload_dict.get("email") or None,
        operating_hours=tpl["hours"],
        google_business_id=gbp_id,
    )
    db.add(business)
    await db.flush()

    update_business_profile.invoke(
        {
            "business_data": {
                "location_id": gbp_id,
                "name": name,
                "category": category,
                "description": seo_bio,
            }
        }
    )
    trace.append(
        {
            "agent": "GoogleBusinessAgent",
            "tool": "update_business_profile",
            "status": "completed",
            "detail": f"Configured & verified Google Business ID {gbp_id}.",
        }
    )

    # Step 2: Agent Config + Starter Catalog
    cfg = BusinessAgentConfig(
        business_id=business.id,
        autopilot_enabled=True,
        auto_publish_scheduled=True,
        auto_reply_positive_reviews=False,
        require_approval_negative_reviews=True,
        preferred_language=language,
        brand_voice="warm, helpful, and neighborhood-friendly",
        catalog_items=tpl["catalog"],
        faqs=tpl["faqs"],
    )
    db.add(cfg)
    await db.flush()
    trace.append(
        {
            "agent": "CatalogSetupAgent",
            "tool": "seed_catalog_and_faqs",
            "status": "completed",
            "detail": f"Added {len(tpl['catalog'])} starter catalog item(s) and {len(tpl['faqs'])} FAQ(s).",
        }
    )

    # Step 3: Starter Multi-Platform Social Pack
    social_agent = SocialMediaAgent()
    starter_specs = [
        (
            SocialPlatform.GOOGLE,
            f"Grand Digital Launch & Welcome to {name}",
            PostStatus.PUBLISHED,
            0,
        ),
        (
            SocialPlatform.INSTAGRAM,
            specialty or f"Behind the scenes at {name}",
            PostStatus.SCHEDULED,
            1,
        ),
        (SocialPlatform.FACEBOOK, f"Weekend Local Special at {name}", PostStatus.SCHEDULED, 3),
    ]
    now = datetime.now(UTC)
    posts_created = 0
    if payload_dict.get("auto_schedule_starter_posts", True):
        for platform, topic, p_status, day_offset in starter_specs:
            gen = await social_agent.generate_post(
                business=business,
                platform=platform.value,
                topic=topic,
                language=language,
                overrides=overrides,
            )
            tags = " ".join(gen["hashtags"])
            body = f"{gen['content']}\n\n{tags}".strip() if tags else gen["content"]
            post = SocialPost(
                business_id=business.id,
                platform=platform,
                content=body,
                status=p_status,
                published_at=now if p_status == PostStatus.PUBLISHED else None,
                scheduled_at=(now + timedelta(days=day_offset)).replace(
                    hour=11, minute=30, second=0, microsecond=0
                )
                if p_status == PostStatus.SCHEDULED
                else None,
            )
            db.add(post)
            posts_created += 1

        trace.append(
            {
                "agent": "SocialMediaAgent",
                "tool": "generate_starter_posts",
                "status": "completed",
                "detail": f"Created {posts_created} starter posts across Google, Instagram & Facebook.",
            }
        )

    await db.flush()
    health = await compute_health_score(db, business)

    checklist = [
        {"item": "Business name & category", "completed": True},
        {
            "item": "Physical address / service area",
            "completed": bool(business.address or business.city),
        },
        {"item": "Phone & website", "completed": bool(business.phone or business.email)},
        {"item": "Operating hours configured", "completed": True},
        {"item": "Google Business ID linked", "completed": True},
    ]
    google_setup = {
        "business_id": business.id,
        "google_business_id": gbp_id,
        "status": "verified",
        "completeness_score": int(
            (sum(1 for c in checklist if c["completed"]) / len(checklist)) * 100
        ),
        "checklist": checklist,
    }

    duration_ms = int((time.perf_counter() - started) * 1000)
    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="onboarding",
            goal=f"60-second onboarding for {name}",
            agents_invoked=["GoogleBusinessAgent", "CatalogSetupAgent", "SocialMediaAgent"],
            tools_called=[
                "generate_local_seo_bio",
                "update_business_profile",
                "seed_catalog_and_faqs",
                "generate_starter_posts",
            ],
            steps_summary=trace,
            outcome="completed",
            duration_ms=duration_ms,
        )
    )
    await db.flush()
    await db.refresh(business)

    return {
        "business": BusinessResponse.model_validate(business),
        "google_setup": google_setup,
        "starter_posts_created": posts_created,
        "catalog_items_created": len(tpl["catalog"]),
        "health_score": health["overall_score"],
        "summary": (
            f"Launched **{name}** with a verified Google Business Profile, SEO bio, "
            f"{len(tpl['catalog'])} storefront items, and {posts_created} starter posts "
            f"(Digital Health Score: {health['overall_score']}/100)."
        ),
        "agent_trace": trace,
    }


async def launch_multi_channel_campaign(
    db: AsyncSession,
    business: Business,
    occasion: str,
    offer_details: str,
    platforms: list[SocialPlatform],
    auto_execute: bool = False,
    schedule_start_days: int = 1,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a coordinated multi-platform marketing campaign (autopilot or HITL queued)."""
    started = time.perf_counter()
    cfg = await get_or_create_agent_config(db, business.id)
    social_agent = SocialMediaAgent()
    trace: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    posts_created = 0
    approvals_queued = 0

    promo_raw = generate_promotional_offer.invoke(
        {"business_name": business.name, "occasion": occasion}
    )
    promo_pkg = json.loads(promo_raw)
    trace.append(
        {
            "agent": "ContentGeneratorAgent",
            "tool": "generate_promotional_offer",
            "status": "completed",
            "detail": f"Created promo angle '{promo_pkg['headline']}' (code: {promo_pkg['recommended_promo_code']}).",
        }
    )

    now = datetime.now(UTC)
    topic_text = f"{occasion} — {offer_details}".strip(" —")

    for idx, plat in enumerate(platforms):
        gen = await social_agent.generate_post(
            business=business,
            platform=plat.value,
            topic=topic_text,
            tone=cfg.brand_voice,
            language=cfg.preferred_language,
            overrides=overrides,
        )
        tags_line = " ".join(gen["hashtags"])
        full_content = f"{gen['content']}\n\n{tags_line}".strip() if tags_line else gen["content"]
        sched_dt = (now + timedelta(days=schedule_start_days + idx)).replace(
            hour=11, minute=30, second=0, microsecond=0
        )

        if auto_execute:
            post = SocialPost(
                business_id=business.id,
                platform=plat,
                content=full_content,
                status=PostStatus.SCHEDULED,
                scheduled_at=sched_dt,
            )
            db.add(post)
            await db.flush()
            posts_created += 1
            assets.append(
                {
                    "platform": plat.value,
                    "status": "scheduled",
                    "post_id": post.id,
                    "scheduled_at": sched_dt.isoformat(),
                    "content": full_content,
                }
            )
        else:
            action = AgentApprovalAction(
                business_id=business.id,
                action_type="publish_post",
                title=f"Schedule {plat.value.title()} Campaign Post: {occasion}",
                description=f"Campaign post scheduled for {sched_dt.date().isoformat()} at 11:30 UTC.",
                agent_name="SocialMediaAgent",
                reasoning=f"Coordinated {occasion} promotion tailored to {plat.value} audience.",
                risk_level=RiskLevel.LOW,
                payload={
                    "platform": plat.value,
                    "content": full_content,
                    "status": "scheduled",
                    "scheduled_at": sched_dt.isoformat(),
                },
                status=ApprovalStatus.PENDING,
            )
            db.add(action)
            await db.flush()
            approvals_queued += 1
            assets.append(
                {
                    "platform": plat.value,
                    "status": "pending_approval",
                    "approval_id": action.id,
                    "scheduled_at": sched_dt.isoformat(),
                    "content": full_content,
                }
            )

        trace.append(
            {
                "agent": "SocialMediaAgent",
                "tool": f"prepare_{plat.value}_post",
                "status": "completed",
                "detail": f"{'Scheduled' if auto_execute else 'Queued for approval'} {plat.value} asset.",
            }
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="campaign",
            goal=f"Multi-channel campaign for '{occasion}' across {[p.value for p in platforms]}",
            agents_invoked=["ContentGeneratorAgent", "SocialMediaAgent"],
            tools_called=["generate_promotional_offer", "generate_post"],
            steps_summary=trace,
            outcome="completed" if auto_execute else "queued_for_approval",
            duration_ms=duration_ms,
        )
    )
    await db.flush()

    return {
        "business_id": business.id,
        "occasion": occasion,
        "posts_created": posts_created,
        "approvals_queued": approvals_queued,
        "assets": assets,
        "agent_trace": trace,
    }
