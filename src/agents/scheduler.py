"""Autonomous background autopilot scheduler powered by APScheduler."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import get_or_create_agent_config
from src.agents.review_agent import ReviewAgent
from src.database.db import SessionLocal
from src.models.agent_models import (
    AgentApprovalAction,
    AgentRunLog,
    ApprovalStatus,
    RiskLevel,
)
from src.models.business import Business
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPost
from src.utils.logger import get_logger

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_autopilot_cycle_for_business(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Run one autonomous cycle for a single business: publish due posts & triage pending reviews."""
    started = time.perf_counter()
    cfg = await get_or_create_agent_config(db, business.id)
    now = datetime.now(UTC)
    trace: list[dict[str, Any]] = []
    published_posts = 0
    auto_replied = 0
    queued_hitl = 0

    if not cfg.autopilot_enabled:
        return {
            "business_id": business.id,
            "autopilot_enabled": False,
            "published_posts": 0,
            "auto_replied_reviews": 0,
            "queued_approvals": 0,
            "message": "Autopilot is currently paused for this business.",
        }

    # 1. Publish due scheduled social posts
    if cfg.auto_publish_scheduled:
        due_posts = list(
            (
                await db.execute(
                    select(SocialPost).where(
                        SocialPost.business_id == business.id,
                        SocialPost.status == PostStatus.SCHEDULED,
                        SocialPost.scheduled_at.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for post in due_posts:
            sched = post.scheduled_at
            if sched is not None:
                sched_utc = sched if sched.tzinfo else sched.replace(tzinfo=UTC)
                if sched_utc <= now:
                    post.status = PostStatus.PUBLISHED
                    post.published_at = now
                    published_posts += 1

        if published_posts:
            trace.append(
                {
                    "agent": "SocialSchedulerAgent",
                    "tool": "publish_due_posts",
                    "status": "completed",
                    "detail": f"Published {published_posts} scheduled post(s).",
                }
            )

    # 2. Scan pending reviews: auto-reply positive (if enabled) or queue HITL drafts
    pending_reviews = list(
        (
            await db.execute(
                select(Review).where(
                    Review.business_id == business.id,
                    Review.response_status == ResponseStatus.PENDING,
                )
            )
        )
        .scalars()
        .all()
    )

    existing_approvals = list(
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
    queued_review_ids = {
        int(a.payload["review_id"])
        for a in existing_approvals
        if isinstance(a.payload, dict) and a.payload.get("review_id") is not None
    }

    review_agent = ReviewAgent()
    for rev in pending_reviews[:10]:
        if rev.rating >= 4 and cfg.auto_reply_positive_reviews:
            reply_text = await review_agent.draft_response(
                business=business,
                review=rev,
                tone=cfg.brand_voice,
                language=cfg.preferred_language,
            )
            rev.response_text = reply_text
            rev.response_status = ResponseStatus.RESPONDED
            rev.responded_at = now
            auto_replied += 1
        elif rev.id not in queued_review_ids and (
            rev.rating <= 3 or not cfg.auto_reply_positive_reviews
        ):
            draft = await review_agent.draft_response(
                business=business,
                review=rev,
                tone=cfg.brand_voice,
                language=cfg.preferred_language,
            )
            action = AgentApprovalAction(
                business_id=business.id,
                action_type="reply_review",
                title=f"Reply to {rev.reviewer_name} ({rev.rating}★ {rev.platform.title()})",
                description=rev.review_text or "(No written text)",
                agent_name="ReviewWatchdogAgent",
                reasoning=(
                    "Negative/neutral review flagged by autonomous watchdog for human review."
                    if rev.rating <= 3
                    else "Drafted reply waiting for owner approval."
                ),
                risk_level=RiskLevel.HIGH if rev.rating <= 2 else RiskLevel.MEDIUM,
                payload={"review_id": rev.id, "response_text": draft},
                status=ApprovalStatus.PENDING,
            )
            db.add(action)
            queued_hitl += 1

    if auto_replied or queued_hitl:
        trace.append(
            {
                "agent": "ReviewWatchdogAgent",
                "tool": "triage_pending_reviews",
                "status": "completed",
                "detail": f"Auto-replied {auto_replied}, queued {queued_hitl} for HITL approval.",
            }
        )

    if not trace:
        trace.append(
            {
                "agent": "AutopilotMonitor",
                "tool": "health_heartbeat",
                "status": "completed",
                "detail": "Checked scheduled posts and pending reviews — everything up to date.",
            }
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="autopilot",
            goal="Autonomous background check for scheduled posts and pending reviews",
            agents_invoked=list(dict.fromkeys(t["agent"] for t in trace)),
            tools_called=list(dict.fromkeys(t["tool"] for t in trace)),
            steps_summary=trace,
            outcome="completed",
            duration_ms=duration_ms,
        )
    )
    await db.flush()

    return {
        "business_id": business.id,
        "autopilot_enabled": True,
        "published_posts": published_posts,
        "auto_replied_reviews": auto_replied,
        "queued_approvals": queued_hitl,
        "trace": trace,
    }


async def run_all_businesses_autopilot() -> None:
    """Periodic background job running autopilot across all businesses."""
    try:
        async with SessionLocal() as db:
            businesses = list((await db.execute(select(Business))).scalars().all())
            for biz in businesses:
                await run_autopilot_cycle_for_business(db, biz)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Autopilot background cycle encountered an error: %s", exc)


def start_autopilot_scheduler() -> None:
    """Start the APScheduler background worker if not already running."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_all_businesses_autopilot,
        trigger="interval",
        minutes=5,
        id="bizpresence_autopilot",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Autopilot APScheduler started (interval=5m).")


def stop_autopilot_scheduler() -> None:
    """Shut down the APScheduler background worker cleanly."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Autopilot APScheduler stopped.")
    _scheduler = None
