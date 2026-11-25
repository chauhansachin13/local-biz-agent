"""Main BizPresence AI orchestrator coordinating social, review, and booking agents."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.booking_agent import BookingAgent
from src.agents.llm_client import generate_text_with_llm
from src.agents.review_agent import ReviewAgent
from src.agents.social_agent import SocialMediaAgent
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPlatform, SocialPost


class BizPresenceOrchestrator:
    """Routes natural-language user requests across specialized digital presence agents."""

    def __init__(self) -> None:
        self.social_agent = SocialMediaAgent()
        self.review_agent = ReviewAgent()
        self.booking_agent = BookingAgent()

    async def handle_chat(
        self,
        db: AsyncSession,
        business: Business,
        message: str,
        auto_execute: bool = True,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a natural-language prompt, execute requested actions, and return response."""
        text = message.strip()
        low = text.lower()
        actions_taken: list[str] = []
        data: dict[str, Any] = {}
        followups: list[str] = []

        intent = self._classify_intent(low)

        if intent == "social_create":
            platform_str = self._extract_platform(low)
            topic = self._extract_topic(text)
            generated = await self.social_agent.generate_post(
                business=business,
                platform=platform_str,
                topic=topic,
                overrides=context,
            )
            data["generated_post"] = generated

            if auto_execute and any(
                k in low for k in ("schedule", "publish", "post it", "create", "draft")
            ):
                is_schedule = "schedule" in low
                is_draft = "draft" in low and not is_schedule
                post_status = (
                    PostStatus.SCHEDULED
                    if is_schedule
                    else (PostStatus.DRAFT if is_draft else PostStatus.PUBLISHED)
                )
                now = datetime.now(timezone.utc)
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
                actions_taken.append(
                    f"Created {post_status.value} {platform_str} post (ID #{post.id})"
                )
                data["post_id"] = post.id
                data["status"] = post_status.value

            hashtags_str = " ".join(generated["hashtags"])
            reply = (
                f"Here is a {generated['platform'].title()} post for **{business.name}**:\n\n"
                f"> {generated['content']}\n\n"
                f"**Hashtags:** {hashtags_str or 'None'}\n"
                f"**Best time to post:** {generated['best_time_to_post']}"
            )
            if actions_taken:
                reply += f"\n\n✅ Action completed: {actions_taken[0]}."
            followups = [
                "Schedule this post for tomorrow morning",
                "Create a matching Facebook post",
                "Show my upcoming content calendar",
            ]

        elif intent == "review_respond":
            stmt = (
                select(Review)
                .where(
                    Review.business_id == business.id,
                    Review.response_status == ResponseStatus.PENDING,
                )
                .order_by(Review.created_at.desc())
            )
            pending = (await db.execute(stmt)).scalars().all()

            if not pending:
                reply = (
                    f"Great news! **{business.name}** has 0 pending reviews—all customer "
                    "reviews have already been responded to."
                )
                followups = [
                    "Give me a summary of our performance",
                    "Write a social post highlighting a 5-star review",
                ]
            else:
                do_auto = auto_execute and any(
                    k in low for k in ("auto", "all", "respond to", "reply to", "send")
                )
                drafts = []
                now = datetime.now(timezone.utc)
                for rev in pending[:10]:
                    draft = await self.review_agent.draft_response(
                        business=business, review=rev, overrides=context
                    )
                    if do_auto:
                        rev.response_text = draft
                        rev.response_status = ResponseStatus.RESPONDED
                        rev.responded_at = now
                    drafts.append(
                        {
                            "review_id": rev.id,
                            "reviewer": rev.reviewer_name,
                            "rating": rev.rating,
                            "draft": draft,
                        }
                    )
                if do_auto:
                    await db.flush()
                    actions_taken.append(f"Auto-responded to {len(drafts)} pending review(s)")
                    reply = (
                        f"I drafted and published replies to **{len(drafts)} pending review(s)** "
                        f"for **{business.name}**."
                    )
                else:
                    actions_taken.append(f"Drafted AI replies for {len(drafts)} pending review(s)")
                    preview = "\n".join(
                        f"- **{d['reviewer']} ({d['rating']}★):** {d['draft']}"
                        for d in drafts[:3]
                    )
                    reply = (
                        f"You have **{len(pending)} pending review(s)**. Here are AI-drafted replies:\n\n"
                        f"{preview}"
                    )
                data["drafts"] = drafts
                followups = [
                    "Auto-respond to all pending reviews",
                    "Give me a summary of our performance",
                ]

        elif intent == "booking_manage":
            today = date.today()
            stmt = (
                select(Booking)
                .where(
                    Booking.business_id == business.id,
                    Booking.booking_date >= today,
                    Booking.status != BookingStatus.CANCELLED,
                )
                .order_by(Booking.booking_date.asc(), Booking.booking_time.asc())
            )
            upcoming = (await db.execute(stmt)).scalars().all()
            avail = await self.booking_agent.get_availability(db, business, today)
            open_slots = [s["start_time"] for s in avail["slots"] if s["available"]]
            data["upcoming_count"] = len(upcoming)
            data["today_open_slots"] = open_slots[:8]

            if upcoming:
                lines = "\n".join(
                    f"- **{b.booking_date} {b.booking_time.strftime('%H:%M')}** — "
                    f"{b.customer_name} ({b.service}, {b.status.value})"
                    for b in upcoming[:5]
                )
                reply = (
                    f"**{business.name}** has **{len(upcoming)} upcoming booking(s)**:\n\n{lines}\n\n"
                    f"**Open slots today:** {', '.join(open_slots[:6]) if open_slots else 'Fully booked / Closed'}"
                )
            else:
                reply = (
                    f"No upcoming bookings found for **{business.name}**. "
                    f"Open slots today: {', '.join(open_slots[:6]) if open_slots else 'Closed today'}."
                )
            followups = [
                "Promote open slots on Instagram",
                "Give me a summary of our performance",
            ]

        elif intent == "analytics_overview":
            reviews = (
                await db.execute(select(Review).where(Review.business_id == business.id))
            ).scalars().all()
            posts = (
                await db.execute(select(SocialPost).where(SocialPost.business_id == business.id))
            ).scalars().all()
            bookings = (
                await db.execute(select(Booking).where(Booking.business_id == business.id))
            ).scalars().all()

            avg_rating = (
                round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 0.0
            )
            pending_rev = sum(
                1 for r in reviews if r.response_status == ResponseStatus.PENDING
            )
            upcoming_bk = sum(
                1
                for b in bookings
                if b.booking_date >= date.today() and b.status != BookingStatus.CANCELLED
            )
            gbp_status = "verified" if business.google_business_id else "not_configured"
            data = {
                "total_reviews": len(reviews),
                "average_rating": avg_rating,
                "pending_reviews": pending_rev,
                "total_posts": len(posts),
                "upcoming_bookings": upcoming_bk,
                "google_profile_status": gbp_status,
            }
            reply = (
                f"Here is the live digital presence snapshot for **{business.name}**:\n\n"
                f"- **Reviews:** {len(reviews)} total ({avg_rating}★ avg, {pending_rev} pending reply)\n"
                f"- **Social Posts:** {len(posts)} total posts\n"
                f"- **Upcoming Bookings:** {upcoming_bk}\n"
                f"- **Google Business Profile:** `{gbp_status}`"
            )
            followups = [
                "Auto-respond to pending reviews",
                "Create an Instagram post for this week",
            ]

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
                    select(func.count(SocialPost.id)).where(SocialPost.business_id == business.id)
                )
            ).scalar_one()
            next_avail = await self.booking_agent.next_available_summary(db, business)

            llm_reply = await generate_text_with_llm(
                system_prompt=(
                    f"You are BizPresence AI, a helpful digital presence assistant for {business.name} "
                    f"({business.category} in {business.city or ''}, {business.state or ''}). "
                    "Give practical, concise guidance."
                ),
                user_prompt=(
                    f"Context: {rev_count} reviews ({pending_count} pending), {posts_count} social posts, "
                    f"next booking slots: {next_avail}.\nUser asks: {text}"
                ),
                overrides=context,
                temperature=0.7,
                max_tokens=350,
            )

            reply = llm_reply or (
                f"I'm ready to help grow **{business.name}**! Right now you have **{rev_count} reviews** "
                f"({pending_count} pending reply), **{posts_count} social posts**, and open booking slots "
                f"{next_avail}.\n\n"
                "Ask me to:\n"
                "- Write or schedule an Instagram, Facebook, or Google post\n"
                "- Draft or auto-send replies to pending customer reviews\n"
                "- Check upcoming bookings and open time slots\n"
                "- Summarize your digital presence performance"
            )
            followups = [
                "Create and schedule an Instagram post about our weekend special",
                "Draft responses for pending reviews",
                "Show today's bookings and open slots",
            ]

        return {
            "business_id": business.id,
            "reply": reply,
            "intent": intent,
            "actions_taken": actions_taken,
            "data": data,
            "suggested_followups": followups,
        }

    async def generate_suggestions(
        self, db: AsyncSession, business: Business
    ) -> list[dict[str, Any]]:
        """Analyze business database state and return prioritized AI suggestions."""
        suggestions: list[dict[str, Any]] = []

        pending_reviews = (
            await db.execute(
                select(func.count(Review.id)).where(
                    Review.business_id == business.id,
                    Review.response_status == ResponseStatus.PENDING,
                )
            )
        ).scalar_one()

        negative_pending = (
            await db.execute(
                select(func.count(Review.id)).where(
                    Review.business_id == business.id,
                    Review.response_status == ResponseStatus.PENDING,
                    Review.rating <= 3,
                )
            )
        ).scalar_one()

        if negative_pending > 0:
            suggestions.append(
                {
                    "id": "sug_negative_reviews",
                    "category": "reviews",
                    "priority": "high",
                    "title": f"Respond urgently to {negative_pending} low-rating review(s)",
                    "description": (
                        "Timely, empathetic responses to sub-3-star reviews protect local trust "
                        "and often turn unhappy guests into repeat visitors."
                    ),
                    "recommended_action": "Draft empathetic review replies",
                    "prompt_to_run": "Draft responses for all pending reviews",
                }
            )
        elif pending_reviews > 0:
            suggestions.append(
                {
                    "id": "sug_pending_reviews",
                    "category": "reviews",
                    "priority": "medium",
                    "title": f"Reply to {pending_reviews} pending customer review(s)",
                    "description": (
                        "Businesses that respond to >80% of customer reviews see stronger Google Maps ranking."
                    ),
                    "recommended_action": "Auto-respond to pending reviews",
                    "prompt_to_run": "Auto-respond to all pending reviews",
                }
            )

        if not business.google_business_id:
            suggestions.append(
                {
                    "id": "sug_gbp_setup",
                    "category": "google_business",
                    "priority": "high",
                    "title": "Link & verify your Google Business Profile",
                    "description": (
                        "Connecting a Google Business ID unlocks local map insights and direct Google Posts."
                    ),
                    "recommended_action": "Configure Google Profile in Settings",
                    "prompt_to_run": "Give me a summary of our performance",
                }
            )

        scheduled_posts = (
            await db.execute(
                select(func.count(SocialPost.id)).where(
                    SocialPost.business_id == business.id,
                    SocialPost.status == PostStatus.SCHEDULED,
                )
            )
        ).scalar_one()

        if scheduled_posts == 0:
            suggestions.append(
                {
                    "id": "sug_social_schedule",
                    "category": "social",
                    "priority": "medium",
                    "title": "Schedule fresh social media content this week",
                    "description": (
                        f"You currently have 0 scheduled posts. Consistency keeps {business.name} "
                        "top-of-mind for local customers."
                    ),
                    "recommended_action": "Create & schedule an Instagram post",
                    "prompt_to_run": "Create and schedule an Instagram post about our featured service",
                }
            )

        today_bookings = (
            await db.execute(
                select(func.count(Booking.id)).where(
                    Booking.business_id == business.id,
                    Booking.booking_date == date.today(),
                    Booking.status != BookingStatus.CANCELLED,
                )
            )
        ).scalar_one()

        if today_bookings < 2:
            suggestions.append(
                {
                    "id": "sug_fill_slots",
                    "category": "bookings",
                    "priority": "low",
                    "title": "Promote open booking slots today",
                    "description": (
                        f"Only {today_bookings} booking(s) on the books for today. Share a same-day call-out."
                    ),
                    "recommended_action": "Generate same-day promo post",
                    "prompt_to_run": "Create an Instagram post inviting guests to book open slots today",
                }
            )

        if not suggestions:
            suggestions.append(
                {
                    "id": "sug_testimonial_post",
                    "category": "growth",
                    "priority": "low",
                    "title": "Turn a 5-star review into social proof",
                    "description": "Sharing customer praise builds trust with nearby first-time visitors.",
                    "recommended_action": "Generate testimonial spotlight",
                    "prompt_to_run": "Create an Instagram post celebrating our 5-star customer reviews",
                }
            )

        return suggestions

    def _classify_intent(self, low: str) -> str:
        if any(
            k in low
            for k in (
                "post",
                "instagram",
                "facebook",
                "twitter",
                "social",
                "caption",
                "hashtag",
                "content",
            )
        ):
            return "social_create"
        if any(k in low for k in ("review", "rating", "feedback", "respond", "reply")):
            return "review_respond"
        if any(
            k in low
            for k in ("book", "booking", "appointment", "reservation", "slot", "availability")
        ):
            return "booking_manage"
        if any(
            k in low
            for k in ("summary", "overview", "status", "analytics", "performance", "metrics")
        ):
            return "analytics_overview"
        return "general"

    def _extract_platform(self, low: str) -> str:
        for p in ("instagram", "facebook", "google", "twitter"):
            if p in low:
                return p
        return "instagram"

    def _extract_topic(self, text: str) -> str:
        match = re.search(r"(?:about|for|highlighting|on)\s+(.+)", text, re.IGNORECASE)
        return match.group(1).strip().rstrip(".!") if match else ""
