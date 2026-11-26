"""LangGraph StateGraph multi-agent supervisor with memory, planning, tool trace, and HITL guardrails."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.booking_agent import BookingAgent
from src.agents.health_and_growth import compute_health_score, get_or_create_agent_config
from src.agents.llm_client import generate_text_with_llm
from src.agents.loyalty_and_engagement import (
    generate_content_calendar,
    get_campaign_analytics,
    get_content_calendar,
    get_loyalty_analytics,
    get_nps_analytics,
    list_gift_cards,
)
from src.agents.revenue_and_growth import compute_revenue_analytics
from src.agents.review_agent import ReviewAgent
from src.agents.social_agent import SocialMediaAgent
from src.models.agent_models import (
    AgentApprovalAction,
    AgentRunLog,
    AgentThreadMessage,
    ApprovalStatus,
    BusinessAgentConfig,
    OrderRequest,
    OrderStatus,
    RiskLevel,
    WhatsAppMessage,
)
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPlatform, SocialPost
from src.tools.analytics_tools import aggregate_platform_metrics
from src.tools.content_tools import generate_post_ideas
from src.tools.google_tools import get_business_insights, post_google_update
from src.tools.review_tools import analyze_review_sentiment, flag_critical_review


class SupervisorState(TypedDict, total=False):
    """State passed across LangGraph supervisor nodes."""

    business_id: int
    session_id: str
    message: str
    auto_execute: bool
    language: str
    overrides: dict[str, Any]
    history_summary: str
    plan: list[str]
    primary_intent: str
    agent_trace: list[dict[str, Any]]
    actions_taken: list[str]
    queued_approvals: list[dict[str, Any]]
    section_replies: list[str]
    data: dict[str, Any]
    suggested_followups: list[str]
    health_score: int
    reply: str
    started_at: float


_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "social_create",
        (
            "post",
            "instagram",
            "facebook",
            "twitter",
            "social",
            "caption",
            "hashtag",
            "content",
            "campaign",
        ),
    ),
    ("review_respond", ("review", "rating", "feedback", "respond", "reply")),
    ("booking_manage", ("book", "booking", "appointment", "reservation", "slot", "availability")),
    ("order_manage", ("order", "orders", "delivery", "pickup", "takeaway", "menu")),
    ("google_profile", ("google", "gbp", "profile", "hours", "seo", "insights", "maps")),
    (
        "revenue_roi",
        ("revenue", "roi", "sales", "coupon", "coupons", "promo", "waitlist", "top seller"),
    ),
    (
        "loyalty_engagement",
        (
            "loyalty",
            "points",
            "gift card",
            "giftcard",
            "nps",
            "survey",
            "email campaign",
            "newsletter",
            "content calendar",
        ),
    ),
    (
        "analytics_overview",
        ("summary", "overview", "status", "analytics", "performance", "metrics", "health", "audit"),
    ),
]


def _detect_intents_offline(low: str) -> list[str]:
    """Extract ordered multi-intent plan from a compound natural-language request."""
    matched: list[str] = []
    for intent_name, keywords in _INTENT_RULES:
        if any(kw in low for kw in keywords):
            # Avoid matching 'google' alone as google_profile when the user clearly asked for a Google post
            if (
                intent_name == "google_profile"
                and "social_create" in matched
                and not any(
                    w in low for w in ("gbp", "profile", "hours", "seo", "insights", "maps")
                )
            ):
                continue
            matched.append(intent_name)
    # Prevent 'content' in 'content calendar' or 'campaign' in 'email campaign' from spuriously triggering social_create
    if "loyalty_engagement" in matched and "social_create" in matched:
        explicit_social = any(
            w in low
            for w in (
                "instagram",
                "facebook",
                "twitter",
                "social",
                "caption",
                "hashtag",
                "publish post",
                "write post",
                "create post",
            )
        )
        if not explicit_social:
            matched = [m for m in matched if m != "social_create"]
    return matched or ["general"]


def _extract_platform(low: str) -> str:
    for plat in ("instagram", "facebook", "google", "twitter"):
        if plat in low:
            return plat
    return "instagram"


def _extract_topic(text: str) -> str:
    match = re.search(
        r"(?:about|for|highlighting|on)\s+(.+?)(?:\s+and\s+(?:check|show|reply|respond|audit)|$)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip().rstrip(".!") if match else ""


async def run_supervisor_turn(
    db: AsyncSession,
    business: Business,
    message: str,
    auto_execute: bool = True,
    session_id: str = "default",
    language: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a full LangGraph Supervisor turn with memory, planning, tools, and HITL."""
    cfg: BusinessAgentConfig = await get_or_create_agent_config(db, business.id)
    resolved_language = (language or cfg.preferred_language or "English").strip()
    overrides = context or {}

    # Load last 6 messages for multi-turn memory
    hist_stmt = (
        select(AgentThreadMessage)
        .where(
            AgentThreadMessage.business_id == business.id,
            AgentThreadMessage.session_id == session_id,
        )
        .order_by(AgentThreadMessage.created_at.desc())
        .limit(6)
    )
    recent_msgs = list((await db.execute(hist_stmt)).scalars().all())
    recent_msgs.reverse()
    history_summary = "\n".join(f"{m.role.upper()}: {m.content[:180]}" for m in recent_msgs)

    social_agent = SocialMediaAgent()
    review_agent = ReviewAgent()
    booking_agent = BookingAgent()

    async def plan_node(state: SupervisorState) -> SupervisorState:
        text = state["message"].strip()
        low = text.lower()
        plan = _detect_intents_offline(low)

        # Optionally refine multi-step plan with LLM when API key is configured
        llm_plan_raw = await generate_text_with_llm(
            system_prompt=(
                "You are an AI Supervisor Planner for a local business assistant. "
                "Classify the user message into 1 to 3 ordered tasks from this exact list: "
                "['social_create', 'review_respond', 'booking_manage', 'order_manage', "
                "'google_profile', 'revenue_roi', 'loyalty_engagement', 'analytics_overview', 'general']. "
                'Reply ONLY with a JSON array of strings, e.g. ["social_create", "review_respond"].'
            ),
            user_prompt=(
                f"Recent conversation:\n{state.get('history_summary') or '(none)'}\n\n"
                f"Current request: {text}"
            ),
            overrides=overrides,
            temperature=0.0,
            max_tokens=80,
        )
        if llm_plan_raw:
            try:
                parsed = json.loads(
                    llm_plan_raw.strip()
                    .removeprefix("```json")
                    .removeprefix("```")
                    .removesuffix("```")
                    .strip()
                )
                allowed = {
                    "social_create",
                    "review_respond",
                    "booking_manage",
                    "order_manage",
                    "google_profile",
                    "revenue_roi",
                    "loyalty_engagement",
                    "analytics_overview",
                    "general",
                }
                if isinstance(parsed, list):
                    valid = [t for t in parsed if isinstance(t, str) and t in allowed]
                    if valid:
                        plan = valid[:3]
            except (ValueError, TypeError):
                pass

        trace = list(state.get("agent_trace") or [])
        trace.append(
            {
                "agent": "SupervisorPlanner",
                "tool": "decompose_tasks",
                "status": "completed",
                "detail": f"Planned {len(plan)} step(s): {' → '.join(plan)}",
            }
        )
        return {
            "plan": plan,
            "primary_intent": plan[0],
            "agent_trace": trace,
        }

    async def execute_node(state: SupervisorState) -> SupervisorState:
        text = state["message"].strip()
        low = text.lower()
        plan = state.get("plan") or ["general"]
        can_execute = state.get("auto_execute", True)

        trace = list(state.get("agent_trace") or [])
        actions_taken: list[str] = []
        queued_approvals: list[dict[str, Any]] = []
        sections: list[str] = []
        data: dict[str, Any] = {}
        followups: list[str] = []

        for step in plan:
            if step == "social_create":
                platform_str = _extract_platform(low)
                topic = _extract_topic(text)
                generated = await social_agent.generate_post(
                    business=business,
                    platform=platform_str,
                    topic=topic,
                    tone=cfg.brand_voice,
                    language=resolved_language,
                    overrides=overrides,
                )
                ideas = generate_post_ideas.invoke({"business_type": business.category, "count": 2})
                data["generated_post"] = generated
                data["post_ideas"] = ideas

                wants_action = any(
                    k in low
                    for k in ("schedule", "publish", "post it", "create", "draft", "campaign")
                )
                is_schedule = "schedule" in low
                is_draft = "draft" in low and not is_schedule
                now = datetime.now(UTC)
                scheduled_at = (
                    (now + timedelta(days=1)).replace(hour=11, minute=30, second=0, microsecond=0)
                    if is_schedule
                    else None
                )
                hashtags_line = " ".join(generated["hashtags"])
                full_content = (
                    f"{generated['content']}\n\n{hashtags_line}".strip()
                    if hashtags_line
                    else generated["content"]
                )

                if wants_action and can_execute:
                    post_status = (
                        PostStatus.SCHEDULED
                        if is_schedule
                        else (PostStatus.DRAFT if is_draft else PostStatus.PUBLISHED)
                    )
                    post = SocialPost(
                        business_id=business.id,
                        platform=SocialPlatform(platform_str),
                        content=full_content,
                        status=post_status,
                        scheduled_at=scheduled_at,
                        published_at=now if post_status == PostStatus.PUBLISHED else None,
                    )
                    db.add(post)
                    await db.flush()
                    if platform_str == "google" and business.google_business_id:
                        post_google_update.invoke(
                            {
                                "location_id": business.google_business_id,
                                "content": full_content,
                            }
                        )
                    actions_taken.append(
                        f"Created {post_status.value} {platform_str} post (ID #{post.id})"
                    )
                    data["post_id"] = post.id
                    data["status"] = post_status.value
                    trace.append(
                        {
                            "agent": "SocialMediaAgent",
                            "tool": "create_social_post",
                            "status": "completed",
                            "detail": f"Saved {post_status.value} {platform_str} post #{post.id}.",
                        }
                    )
                elif wants_action and not can_execute:
                    action = AgentApprovalAction(
                        business_id=business.id,
                        action_type="publish_post",
                        title=f"Publish {platform_str.title()} Post",
                        description=f"AI-generated {platform_str} post awaiting owner approval.",
                        agent_name="SocialMediaAgent",
                        reasoning="Copilot mode requires human confirmation before publishing.",
                        risk_level=RiskLevel.LOW,
                        payload={
                            "platform": platform_str,
                            "content": full_content,
                            "status": "scheduled" if is_schedule else "published",
                            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                        },
                        status=ApprovalStatus.PENDING,
                    )
                    db.add(action)
                    await db.flush()
                    queued_approvals.append(
                        {
                            "id": action.id,
                            "action_type": action.action_type,
                            "title": action.title,
                            "risk_level": action.risk_level.value,
                        }
                    )
                    trace.append(
                        {
                            "agent": "SocialMediaAgent",
                            "tool": "queue_approval",
                            "status": "awaiting_approval",
                            "detail": f"Queued {platform_str} post in Approval Inbox (#{action.id}).",
                        }
                    )
                else:
                    trace.append(
                        {
                            "agent": "SocialMediaAgent",
                            "tool": "generate_post",
                            "status": "completed",
                            "detail": f"Drafted {platform_str} copy and hashtags.",
                        }
                    )

                hashtags_str = " ".join(generated["hashtags"])
                sec = (
                    f"Here is a {generated['platform'].title()} post for **{business.name}**:\n\n"
                    f"> {generated['content']}\n\n"
                    f"**Hashtags:** {hashtags_str or 'None'}\n"
                    f"**Best time to post:** {generated['best_time_to_post']}"
                )
                if actions_taken:
                    sec += f"\n\n✅ Action completed: {actions_taken[-1]}."
                elif queued_approvals:
                    sec += "\n\n🟡 Queued in **Approval Inbox** so you can review & publish with 1 click."
                sections.append(sec)
                followups.extend(
                    [
                        "Schedule this post for tomorrow morning",
                        "Launch a 3-platform weekend campaign",
                        "Show my upcoming content calendar",
                    ]
                )

            elif step == "review_respond":
                stmt = (
                    select(Review)
                    .where(
                        Review.business_id == business.id,
                        Review.response_status == ResponseStatus.PENDING,
                    )
                    .order_by(Review.created_at.desc())
                )
                pending = list((await db.execute(stmt)).scalars().all())
                if not pending:
                    sections.append(
                        f"Great news! **{business.name}** has 0 pending reviews—all customer "
                        "reviews have already been responded to."
                    )
                    trace.append(
                        {
                            "agent": "ReviewManagerAgent",
                            "tool": "fetch_pending_reviews",
                            "status": "completed",
                            "detail": "0 pending reviews found.",
                        }
                    )
                else:
                    existing_ap_rows = list(
                        (
                            await db.execute(
                                select(AgentApprovalAction).where(
                                    AgentApprovalAction.business_id == business.id,
                                    AgentApprovalAction.action_type == "reply_review",
                                    AgentApprovalAction.status == ApprovalStatus.PENDING,
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    already_queued_reviews: dict[int, AgentApprovalAction] = {
                        int(a.payload["review_id"]): a
                        for a in existing_ap_rows
                        if isinstance(a.payload, dict) and a.payload.get("review_id") is not None
                    }

                    do_auto = can_execute and any(
                        k in low for k in ("auto", "all", "respond to", "reply to", "send")
                    )
                    drafts: list[dict[str, Any]] = []
                    now = datetime.now(UTC)
                    auto_sent_count = 0
                    for rev in pending[:10]:
                        sent_info = analyze_review_sentiment.invoke(
                            {"review_text": rev.review_text or ""}
                        )
                        if sent_info.get("requires_escalation"):
                            flag_critical_review.invoke(
                                {
                                    "platform": rev.platform,
                                    "review_id": str(rev.id),
                                    "reason": "Negative review flagged by sentiment guardrail",
                                    "severity": "high",
                                }
                            )
                        draft = await review_agent.draft_response(
                            business=business,
                            review=rev,
                            tone=cfg.brand_voice,
                            language=resolved_language,
                            overrides=overrides,
                        )
                        needs_hitl = (
                            rev.rating <= 2 and cfg.require_approval_negative_reviews
                        ) or not do_auto

                        if do_auto and not needs_hitl:
                            rev.response_text = draft
                            rev.response_status = ResponseStatus.RESPONDED
                            rev.responded_at = now
                            auto_sent_count += 1
                            auto_ids = data.setdefault("auto_replied_review_ids", [])
                            auto_ids.append(rev.id)
                        elif not can_execute or (do_auto and needs_hitl):
                            if rev.id in already_queued_reviews:
                                action = already_queued_reviews[rev.id]
                            else:
                                action = AgentApprovalAction(
                                    business_id=business.id,
                                    action_type="reply_review",
                                    title=f"Reply to {rev.reviewer_name} ({rev.rating}★ on {rev.platform.title()})",
                                    description=rev.review_text or "(Rating only)",
                                    agent_name="ReviewManagerAgent",
                                    reasoning=(
                                        "Low-rating review held by safety guardrail for owner approval."
                                        if rev.rating <= 2
                                        else "Copilot mode draft awaiting owner confirmation."
                                    ),
                                    risk_level=RiskLevel.HIGH if rev.rating <= 2 else RiskLevel.LOW,
                                    payload={"review_id": rev.id, "response_text": draft},
                                    status=ApprovalStatus.PENDING,
                                )
                                db.add(action)
                                await db.flush()
                                already_queued_reviews[rev.id] = action
                                queued_approvals.append(
                                    {
                                        "id": action.id,
                                        "action_type": action.action_type,
                                        "title": action.title,
                                        "risk_level": action.risk_level.value,
                                    }
                                )

                        drafts.append(
                            {
                                "review_id": rev.id,
                                "reviewer": rev.reviewer_name,
                                "rating": rev.rating,
                                "draft": draft,
                            }
                        )

                    await db.flush()
                    data["drafts"] = drafts
                    if auto_sent_count > 0:
                        actions_taken.append(
                            f"Auto-responded to {auto_sent_count} pending review(s)"
                        )
                    if queued_approvals:
                        actions_taken.append(
                            f"Queued {len(queued_approvals)} sensitive/draft reply(ies) for approval"
                        )
                    trace.append(
                        {
                            "agent": "ReviewManagerAgent",
                            "tool": "analyze_and_draft_replies",
                            "status": "completed",
                            "detail": (
                                f"Processed {len(drafts)} pending review(s): "
                                f"{auto_sent_count} published, {len(queued_approvals)} queued for HITL."
                            ),
                        }
                    )

                    preview = "\n".join(
                        f"- **{d['reviewer']} ({d['rating']}★):** {d['draft']}" for d in drafts[:3]
                    )
                    sections.append(
                        f"Processed **{len(pending)} pending review(s)** for **{business.name}** "
                        f"({auto_sent_count} sent automatically, {len(queued_approvals)} awaiting approval):\n\n{preview}"
                    )
                followups.extend(
                    ["Open Approval Inbox to review drafts", "Give me a summary of our performance"]
                )

            elif step == "booking_manage":
                today = date.today()
                target_day = today + timedelta(days=1) if "tomorrow" in low else today
                stmt = (
                    select(Booking)
                    .where(
                        Booking.business_id == business.id,
                        Booking.booking_date >= today,
                        Booking.status != BookingStatus.CANCELLED,
                    )
                    .order_by(Booking.booking_date.asc(), Booking.booking_time.asc())
                )
                upcoming = list((await db.execute(stmt)).scalars().all())
                avail = await booking_agent.get_availability(db, business, target_day)
                open_slots = [s["start_time"] for s in avail["slots"] if s["available"]]
                day_label = "tomorrow" if target_day != today else "today"
                data["upcoming_count"] = len(upcoming)
                data["today_open_slots"] = open_slots[:8]

                trace.append(
                    {
                        "agent": "BookingAgent",
                        "tool": "get_availability",
                        "status": "completed",
                        "detail": f"Found {len(upcoming)} upcoming booking(s) and {len(open_slots)} open slot(s) {day_label}.",
                    }
                )
                if upcoming:
                    lines = "\n".join(
                        f"- **{b.booking_date} {b.booking_time.strftime('%H:%M')}** — "
                        f"{b.customer_name} ({b.service}, {b.status.value})"
                        for b in upcoming[:5]
                    )
                    sections.append(
                        f"**{business.name}** has **{len(upcoming)} upcoming booking(s)**:\n\n{lines}\n\n"
                        f"**Open slots {day_label} ({target_day.isoformat()}):** "
                        f"{', '.join(open_slots[:6]) if open_slots else 'Fully booked / Closed'}"
                    )
                else:
                    sections.append(
                        f"No upcoming bookings found for **{business.name}**. "
                        f"Open slots {day_label} ({target_day.isoformat()}): "
                        f"{', '.join(open_slots[:6]) if open_slots else f'Closed {day_label}'}."
                    )
                followups.append("Promote today's open slots on Instagram")

            elif step == "order_manage":
                orders = list(
                    (
                        await db.execute(
                            select(OrderRequest)
                            .where(OrderRequest.business_id == business.id)
                            .order_by(OrderRequest.created_at.desc())
                            .limit(10)
                        )
                    )
                    .scalars()
                    .all()
                )
                active = [
                    o
                    for o in orders
                    if o.status not in {OrderStatus.COMPLETED, OrderStatus.CANCELLED}
                ]
                data["active_orders_count"] = len(active)
                trace.append(
                    {
                        "agent": "OrderAgent",
                        "tool": "fetch_active_orders",
                        "status": "completed",
                        "detail": f"Found {len(active)} active online order(s) out of {len(orders)} recent.",
                    }
                )
                if active:
                    lines = "\n".join(
                        f"- **Order #{o.id}** — {o.customer_name} ({o.fulfillment_type.value}, "
                        f"${o.total_amount:.2f}, `{o.status.value}`)"
                        for o in active[:5]
                    )
                    sections.append(f"**Active Online Orders ({len(active)}):**\n\n{lines}")
                else:
                    sections.append(
                        f"No active pending orders right now. Share your customer storefront "
                        f"(`/site/{business.id}`) to start receiving online orders!"
                    )

            elif step == "google_profile":
                loc_id = business.google_business_id or f"loc_{business.id}"
                insights = get_business_insights.invoke({"location_id": loc_id, "days": 30})
                data["google_insights"] = insights
                trace.append(
                    {
                        "agent": "GoogleBusinessAgent",
                        "tool": "get_business_insights",
                        "status": "completed",
                        "detail": f"Checked GBP status ({'verified' if business.google_business_id else 'not linked'}) and 30d insights.",
                    }
                )
                summary = insights.get("summary", {})
                sections.append(
                    f"**Google Business Profile ({'Verified ✅' if business.google_business_id else 'Not Linked ⚠️'}):**\n"
                    f"- **Profile Views (30d):** {summary.get('total_views', 'N/A')}\n"
                    f"- **Direction Requests:** {summary.get('direction_requests', 'N/A')} | "
                    f"**Calls:** {summary.get('phone_calls', 'N/A')} | "
                    f"**Website Clicks:** {summary.get('website_clicks', 'N/A')}"
                )

            elif step == "revenue_roi":
                rev_data = await compute_revenue_analytics(db, business)
                data["revenue_analytics"] = rev_data
                trace.append(
                    {
                        "agent": "RevenueGrowthAgent",
                        "tool": "compute_revenue_analytics",
                        "status": "completed",
                        "detail": (
                            f"Estimated total revenue ${rev_data['total_estimated_revenue']:.2f} "
                            f"({rev_data['total_orders']} orders, {rev_data['active_coupons']} active coupons)."
                        ),
                    }
                )
                top_item_str = (
                    ", ".join(
                        f"{t['name']} ({t['units_sold']}×)"
                        for t in rev_data["top_ordered_items"][:3]
                    )
                    or "No items ordered yet"
                )
                sections.append(
                    f"**Revenue & Growth ROI for {business.name}:**\n\n"
                    f"- **Net Online Order Revenue:** ${rev_data['net_order_revenue']:.2f} "
                    f"(Discounts given: ${rev_data['total_discounts_given']:.2f}, AOV: ${rev_data['average_order_value']:.2f})\n"
                    f"- **Estimated Booking Revenue:** ${rev_data['estimated_booking_revenue']:.2f} "
                    f"({rev_data['total_active_bookings']} active bookings)\n"
                    f"- **Total Estimated Revenue:** **${rev_data['total_estimated_revenue']:.2f}**\n"
                    f"- **Repeat Customer Rate:** {rev_data['repeat_customer_rate_pct']}% • "
                    f"**Active Coupons:** {rev_data['active_coupons']} ({rev_data['total_coupon_redemptions']} uses)\n"
                    f"- **Waitlist Guests Waiting:** {rev_data['waitlist_waiting_count']}\n"
                    f"- **Top Items:** {top_item_str}"
                )

            elif step == "loyalty_engagement":
                loy_stats = await get_loyalty_analytics(db, business.id)
                nps_stats = await get_nps_analytics(db, business.id)
                camp_stats = await get_campaign_analytics(db, business.id)
                gift_cards = await list_gift_cards(db, business.id)
                generated_cal: dict[str, Any] | None = None
                if "content calendar" in low and any(
                    w in low for w in ("generate", "create", "build", "plan")
                ):
                    generated_cal = await generate_content_calendar(
                        db, business, days_ahead=7, platforms=["instagram", "facebook"]
                    )
                    actions_taken.append(
                        f"Generated {generated_cal['calendar_entries']} AI content calendar entries"
                    )
                else:
                    cal_entries = await get_content_calendar(db, business.id)
                    data["content_calendar_count"] = len(cal_entries)

                active_gc_balance = round(
                    sum(g["remaining_amount"] for g in gift_cards if g["status"] == "active"), 2
                )
                data["loyalty_analytics"] = loy_stats
                data["nps_analytics"] = nps_stats
                data["email_campaign_analytics"] = camp_stats
                data["active_gift_cards"] = len([g for g in gift_cards if g["status"] == "active"])
                if generated_cal is not None:
                    data["generated_content_calendar"] = generated_cal

                trace.append(
                    {
                        "agent": "LoyaltyEngagementAgent",
                        "tool": "analyze_loyalty_nps_and_campaigns",
                        "status": "completed",
                        "detail": (
                            f"{loy_stats['total_members']} loyalty members, NPS "
                            f"{nps_stats['nps_score'] if nps_stats['nps_score'] is not None else 'N/A'}, "
                            f"{camp_stats['sent_campaigns']} sent email campaigns."
                        ),
                    }
                )
                nps_disp = (
                    f"{nps_stats['nps_score']:+.1f} ({nps_stats['total_responses']} responses)"
                    if nps_stats["nps_score"] is not None
                    else "No responses yet"
                )
                cal_line = (
                    f"- **Content Calendar:** Generated **{generated_cal['calendar_entries']}** 7-day entries!\n"
                    if generated_cal is not None
                    else f"- **Saved Content Calendar Entries:** {data.get('content_calendar_count', 0)}\n"
                )
                sections.append(
                    f"**Loyalty, NPS, Gift Cards & Campaigns for {business.name}:**\n\n"
                    f"- **Loyalty Members:** {loy_stats['total_members']} "
                    f"({loy_stats['total_outstanding_points']:,} pts / "
                    f"${loy_stats['outstanding_liability_dollars']:.2f} liability)\n"
                    f"- **NPS Score:** {nps_disp}\n"
                    f"- **Active Gift Cards:** {data['active_gift_cards']} "
                    f"(${active_gc_balance:.2f} unredeemed balance)\n"
                    f"- **Email Campaigns:** {camp_stats['sent_campaigns']} sent / "
                    f"{camp_stats['total_campaigns']} total "
                    f"(Avg Open: {camp_stats['avg_open_rate_pct']}%)\n"
                    f"{cal_line}"
                )

            elif step == "analytics_overview":
                reviews = list(
                    (await db.execute(select(Review).where(Review.business_id == business.id)))
                    .scalars()
                    .all()
                )
                posts = list(
                    (
                        await db.execute(
                            select(SocialPost).where(SocialPost.business_id == business.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                bookings = list(
                    (await db.execute(select(Booking).where(Booking.business_id == business.id)))
                    .scalars()
                    .all()
                )
                health = await compute_health_score(db, business)
                agg = aggregate_platform_metrics.invoke(
                    {"business_id": str(business.id), "days": 30}
                )
                avg_rating = (
                    round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 0.0
                )
                pending_rev = sum(1 for r in reviews if r.response_status == ResponseStatus.PENDING)
                upcoming_bk = sum(
                    1
                    for b in bookings
                    if b.booking_date >= date.today() and b.status != BookingStatus.CANCELLED
                )
                data.update(
                    {
                        "total_reviews": len(reviews),
                        "average_rating": avg_rating,
                        "pending_reviews": pending_rev,
                        "total_posts": len(posts),
                        "upcoming_bookings": upcoming_bk,
                        "health_score": health["overall_score"],
                        "platform_metrics": agg,
                    }
                )
                trace.append(
                    {
                        "agent": "AnalyticsAgent",
                        "tool": "compute_health_score",
                        "status": "completed",
                        "detail": f"Health Score: {health['overall_score']}/100 (Grade {health['grade']}).",
                    }
                )
                sections.append(
                    f"**Digital Presence Snapshot for {business.name}** "
                    f"(Health Score: **{health['overall_score']}/100 — {health['grade']}**):\n\n"
                    f"- **Reviews:** {len(reviews)} total ({avg_rating}★ avg, {pending_rev} pending reply)\n"
                    f"- **Social Posts:** {len(posts)} total\n"
                    f"- **Upcoming Bookings:** {upcoming_bk}\n"
                    f"- **Top Priority Tip:** {health['top_recommendation']}"
                )

            else:
                rev_count = (
                    await db.execute(
                        select(func.count(Review.id)).where(Review.business_id == business.id)
                    )
                ).scalar_one()
                pending_count = (
                    await db.execute(
                        select(func.count(Review.id)).where(
                            Review.business_id == business.id,
                            Review.response_status == ResponseStatus.PENDING,
                        )
                    )
                ).scalar_one()
                posts_count = (
                    await db.execute(
                        select(func.count(SocialPost.id)).where(
                            SocialPost.business_id == business.id
                        )
                    )
                ).scalar_one()
                next_avail = await booking_agent.next_available_summary(db, business)
                llm_reply = await generate_text_with_llm(
                    system_prompt=(
                        f"You are BizPresence AI, a helpful digital presence assistant for {business.name} "
                        f"({business.category} in {business.city or ''}, {business.state or ''}). "
                        f"Reply in {resolved_language}. Give practical, concise guidance."
                    ),
                    user_prompt=(
                        f"Recent chat:\n{state.get('history_summary') or '(none)'}\n\n"
                        f"Context: {rev_count} reviews ({pending_count} pending), {posts_count} social posts, "
                        f"next booking slots: {next_avail}.\nUser asks: {text}"
                    ),
                    overrides=overrides,
                    temperature=0.7,
                    max_tokens=350,
                )
                trace.append(
                    {
                        "agent": "GeneralAdvisorAgent",
                        "tool": "answer_with_business_context",
                        "status": "completed",
                        "detail": "Generated context-aware guidance.",
                    }
                )
                sections.append(
                    llm_reply
                    or (
                        f"I'm ready to help grow **{business.name}**! Right now you have **{rev_count} reviews** "
                        f"({pending_count} pending reply), **{posts_count} social posts**, and open booking slots "
                        f"{next_avail}.\n\n"
                        "Try asking me multi-step goals like:\n"
                        '- *"Create an Instagram post about our weekend special and check today\'s bookings"*\n'
                        '- *"Draft responses for pending reviews"*\n'
                        '- *"Give me a full digital presence audit"*'
                    )
                )

        health = await compute_health_score(db, business)
        return {
            "agent_trace": trace,
            "actions_taken": actions_taken,
            "queued_approvals": queued_approvals,
            "section_replies": sections,
            "data": data,
            "suggested_followups": followups[:3]
            or [
                "Create an Instagram post about our weekend special",
                "Draft responses for pending reviews",
                "Show my digital presence health audit",
            ],
            "health_score": health["overall_score"],
        }

    async def critic_node(state: SupervisorState) -> SupervisorState:
        """Self-reflection quality critic verifying brand voice, length limits, and empathy."""
        trace = list(state.get("agent_trace") or [])
        data = dict(state.get("data") or {})
        section_replies = list(state.get("section_replies") or [])
        issues_fixed: list[str] = []
        score = 96

        # 1. Inspect generated social post for platform character limits & brand mention
        gen = data.get("generated_post")
        if isinstance(gen, dict):
            plat = str(gen.get("platform", "")).lower()
            orig_content = str(gen.get("content", ""))
            content = orig_content
            if plat == "twitter" and len(content) > 280:
                content = content[:276].rstrip() + "..."
                issues_fixed.append("Trimmed Twitter/X post to <=280 characters")
                score -= 4
            if business.name.lower() not in content.lower():
                suffix = f" — {business.name}"
                if plat == "twitter" and len(content) + len(suffix) > 280:
                    content = content[: 280 - len(suffix) - 3].rstrip() + "..." + suffix
                else:
                    content = f"{content.rstrip()}{suffix}"
                issues_fixed.append("Added business brand mention to social copy")
                score -= 2
            gen["content"] = content
            data["generated_post"] = gen

            # Keep persisted SocialPost / HITL approval consistent with critic revision
            if content != orig_content:
                section_replies = [s.replace(orig_content, content) for s in section_replies]
                tags_line = " ".join(gen.get("hashtags") or [])
                revised_full = f"{content}\n\n{tags_line}".strip() if tags_line else content
                if data.get("post_id") is not None:
                    post_obj = (
                        await db.execute(
                            select(SocialPost).where(SocialPost.id == int(data["post_id"]))
                        )
                    ).scalar_one_or_none()
                    if post_obj:
                        post_obj.content = revised_full
                for q in state.get("queued_approvals") or []:
                    if q.get("action_type") == "publish_post":
                        ap = (
                            await db.execute(
                                select(AgentApprovalAction).where(
                                    AgentApprovalAction.id == int(q["id"])
                                )
                            )
                        ).scalar_one_or_none()
                        if ap:
                            ap_payload = dict(ap.payload or {})
                            ap_payload["content"] = revised_full
                            ap.payload = ap_payload

        # 2. Inspect review reply drafts for empathy & non-defensive phrasing
        drafts = data.get("drafts")
        if isinstance(drafts, list):
            defensive_terms = ("your fault", "you are wrong", "not our problem")
            auto_ids = set(data.get("auto_replied_review_ids") or [])
            for d in drafts:
                txt = str(d.get("draft", ""))
                if any(term in txt.lower() for term in defensive_terms):
                    revised_reply = (
                        f"Thank you for your feedback. At {business.name}, we take every guest's "
                        "experience seriously and would love to discuss this directly with you."
                    )
                    d["draft"] = revised_reply
                    section_replies = [s.replace(txt, revised_reply) for s in section_replies]
                    issues_fixed.append("Rewrote defensive phrasing into empathetic reply")
                    score -= 6
                    rev_id = d.get("review_id")
                    if rev_id in auto_ids:
                        rev_obj = (
                            await db.execute(select(Review).where(Review.id == int(rev_id)))
                        ).scalar_one_or_none()
                        if rev_obj:
                            rev_obj.response_text = revised_reply
                    for q in state.get("queued_approvals") or []:
                        if q.get("action_type") == "reply_review":
                            ap = (
                                await db.execute(
                                    select(AgentApprovalAction).where(
                                        AgentApprovalAction.id == int(q["id"])
                                    )
                                )
                            ).scalar_one_or_none()
                            if ap and (ap.payload or {}).get("review_id") == rev_id:
                                ap_payload = dict(ap.payload or {})
                                ap_payload["response_text"] = revised_reply
                                ap.payload = ap_payload

        if issues_fixed:
            await db.flush()

        data["quality_score"] = max(70, score)
        trace.append(
            {
                "agent": "QualityCriticAgent",
                "tool": "self_reflect_and_validate",
                "status": "completed",
                "detail": (
                    f"Quality score {data['quality_score']}/100 — "
                    + (
                        "; ".join(issues_fixed)
                        if issues_fixed
                        else "All brand & safety checks passed."
                    )
                ),
            }
        )
        return {"agent_trace": trace, "data": data, "section_replies": section_replies}

    async def synthesize_node(state: SupervisorState) -> SupervisorState:
        combined_reply = "\n\n---\n\n".join(state.get("section_replies") or [])
        plan = state.get("plan") or ["general"]
        trace = list(state.get("agent_trace") or [])
        primary_intent = state.get("primary_intent") or plan[0]

        # Persist conversation turns in AgentThreadMessage
        db.add(
            AgentThreadMessage(
                business_id=business.id,
                session_id=session_id,
                role="user",
                content=state["message"],
                intent=primary_intent,
                agent_trace=[],
            )
        )
        db.add(
            AgentThreadMessage(
                business_id=business.id,
                session_id=session_id,
                role="assistant",
                content=combined_reply,
                intent=primary_intent,
                agent_trace=trace,
            )
        )

        # Log full multi-agent run for observability
        duration_ms = int(
            (time.perf_counter() - state.get("started_at", time.perf_counter())) * 1000
        )
        db.add(
            AgentRunLog(
                business_id=business.id,
                trigger_source="chat",
                goal=state["message"],
                agents_invoked=list(dict.fromkeys(t["agent"] for t in trace)),
                tools_called=list(dict.fromkeys(t["tool"] for t in trace)),
                steps_summary=trace,
                outcome="awaiting_approval" if state.get("queued_approvals") else "completed",
                duration_ms=duration_ms,
            )
        )
        await db.flush()
        return {"reply": combined_reply}

    graph = StateGraph(SupervisorState)
    graph.add_node("planner", plan_node)
    graph.add_node("executor", execute_node)
    graph.add_node("critic", critic_node)
    graph.add_node("synthesizer", synthesize_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "critic")
    graph.add_edge("critic", "synthesizer")
    graph.add_edge("synthesizer", END)

    compiled = graph.compile()
    final_state: SupervisorState = await compiled.ainvoke(
        {
            "business_id": business.id,
            "session_id": session_id,
            "message": message,
            "auto_execute": auto_execute,
            "language": resolved_language,
            "overrides": overrides,
            "history_summary": history_summary,
            "agent_trace": [],
            "started_at": time.perf_counter(),
        }
    )

    return {
        "business_id": business.id,
        "reply": final_state["reply"],
        "intent": final_state["primary_intent"],
        "actions_taken": final_state.get("actions_taken") or [],
        "data": final_state.get("data") or {},
        "suggested_followups": final_state.get("suggested_followups") or [],
        "plan": final_state.get("plan") or [],
        "agent_trace": final_state.get("agent_trace") or [],
        "queued_approvals": final_state.get("queued_approvals") or [],
        "health_score": final_state.get("health_score"),
    }


async def decide_approval_action(
    db: AsyncSession,
    business: Business,
    action: AgentApprovalAction,
    decision: str,
    edited_content: str | None = None,
) -> AgentApprovalAction:
    """Approve (optionally with edited content) or reject a queued HITL agent action."""
    now = datetime.now(UTC)
    if decision == "reject":
        action.status = ApprovalStatus.REJECTED
        action.decided_at = now
        await db.flush()
        return action

    payload = dict(action.payload or {})

    if action.action_type == "publish_post":
        content = (edited_content or payload.get("content") or "").strip()
        platform = SocialPlatform(payload.get("platform", "instagram"))
        target_status = payload.get("status", "published")
        sched_raw = payload.get("scheduled_at")
        sched_dt = datetime.fromisoformat(sched_raw) if sched_raw else None
        post_status = (
            PostStatus.SCHEDULED
            if target_status == "scheduled" and sched_dt is not None
            else PostStatus.PUBLISHED
        )
        post = SocialPost(
            business_id=business.id,
            platform=platform,
            content=content,
            status=post_status,
            scheduled_at=sched_dt if post_status == PostStatus.SCHEDULED else None,
            published_at=now if post_status == PostStatus.PUBLISHED else None,
        )
        db.add(post)
        await db.flush()
        payload["executed_post_id"] = post.id
        payload["content"] = content

    elif action.action_type == "reply_review":
        review_id = payload.get("review_id")
        response_text = (edited_content or payload.get("response_text") or "").strip()
        if review_id is not None and response_text:
            rev = (
                await db.execute(
                    select(Review).where(
                        Review.id == int(review_id),
                        Review.business_id == business.id,
                    )
                )
            ).scalar_one_or_none()
            if rev:
                rev.response_text = response_text
                rev.response_status = ResponseStatus.RESPONDED
                rev.responded_at = now
                payload["response_text"] = response_text

    elif action.action_type == "send_loyalty_offer":
        msg_text = (edited_content or payload.get("content") or "").strip()
        phone = str(payload.get("phone") or "on-file")
        cust_name = str(payload.get("customer_name") or "Customer")
        if msg_text:
            db.add(
                WhatsAppMessage(
                    business_id=business.id,
                    sender_phone=phone,
                    sender_name=cust_name,
                    sender_role="assistant",
                    direction="outbound",
                    message_text=msg_text,
                    agent_used="LoyaltyRetentionAgent (Approved)",
                )
            )
            payload["content"] = msg_text

    elif action.action_type == "broadcast_offer":
        msg_text = (edited_content or payload.get("content") or "").strip()
        recipients = list(payload.get("recipients") or [])
        segment = str(payload.get("segment") or "All")
        if msg_text:
            for rec in recipients[:50]:
                cname = str(rec.get("name") or "Friend")
                cphone = str(rec.get("contact") or "crm-on-file")
                first = cname.split()[0] if cname else "Friend"
                personal = (
                    f"Hi {first}, {msg_text[0].lower() + msg_text[1:]}"
                    if len(msg_text) > 1
                    else msg_text
                )
                db.add(
                    WhatsAppMessage(
                        business_id=business.id,
                        sender_phone=cphone,
                        sender_name=cname,
                        sender_role="assistant",
                        direction="outbound",
                        message_text=personal,
                        agent_used=f"BroadcastAgent ({segment} • Approved)",
                    )
                )
            payload["content"] = msg_text

    action.payload = payload
    action.status = ApprovalStatus.EXECUTED
    action.decided_at = now
    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="hitl_approval",
            goal=f"Human approved and executed: {action.title}",
            agents_invoked=[action.agent_name],
            tools_called=[action.action_type],
            steps_summary=[
                {
                    "agent": action.agent_name,
                    "tool": action.action_type,
                    "status": "executed",
                    "detail": f"Approved action #{action.id} executed.",
                }
            ],
            outcome="executed",
            duration_ms=5,
        )
    )
    await db.flush()
    return action
