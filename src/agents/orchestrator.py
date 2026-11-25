"""Main BizPresence AI orchestrator coordinating multi-agent LangGraph execution and suggestions."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.booking_agent import BookingAgent
from src.agents.review_agent import ReviewAgent
from src.agents.social_agent import SocialMediaAgent
from src.agents.supervisor import run_supervisor_turn
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review
from src.models.social_post import PostStatus, SocialPost


class BizPresenceOrchestrator:
    """Routes natural-language requests through the LangGraph multi-agent supervisor."""

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
        session_id: str = "default",
        language: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a natural-language prompt via LangGraph supervisor with memory and HITL."""
        return await run_supervisor_turn(
            db=db,
            business=business,
            message=message,
            auto_execute=auto_execute,
            session_id=session_id,
            language=language,
            context=context,
        )

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
                    "prompt_to_run": "Check our Google Business Profile insights",
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
        for plat in ("instagram", "facebook", "google", "twitter"):
            if plat in low:
                return plat
        return "instagram"

    def _extract_topic(self, text: str) -> str:
        match = re.search(r"(?:about|for|highlighting|on)\s+(.+)", text, re.IGNORECASE)
        return match.group(1).strip().rstrip(".!") if match else ""
