"""Review sentiment analysis and AI response drafting agent."""

from __future__ import annotations

import re
from typing import Any

from src.agents.llm_client import generate_text_with_llm
from src.models.business import Business
from src.models.review import Review, Sentiment

POSITIVE_WORDS = {
    "amazing",
    "awesome",
    "best",
    "clean",
    "delicious",
    "excellent",
    "fantastic",
    "friendly",
    "great",
    "love",
    "loved",
    "outstanding",
    "perfect",
    "professional",
    "recommend",
    "relaxing",
    "wonderful",
}

NEGATIVE_WORDS = {
    "awful",
    "bad",
    "cold",
    "disappointed",
    "expensive",
    "horrible",
    "late",
    "poor",
    "rude",
    "slow",
    "terrible",
    "unprofessional",
    "wait",
    "waited",
    "worst",
}


class ReviewAgent:
    """Analyzes customer review sentiment and drafts personalized responses."""

    def analyze_sentiment(self, rating: int, review_text: str | None) -> Sentiment:
        """Determine Sentiment enum from rating and review text."""
        tokens = set(re.findall(r"[a-zA-Z]+", (review_text or "").lower()))
        pos = len(tokens & POSITIVE_WORDS)
        neg = len(tokens & NEGATIVE_WORDS)
        if rating >= 4 and neg <= pos:
            return Sentiment.POSITIVE
        if rating <= 2 or (neg > pos + 1 and rating <= 3):
            return Sentiment.NEGATIVE
        return Sentiment.NEUTRAL

    async def draft_response(
        self,
        business: Business,
        review: Review,
        tone: str = "warm and professional",
        language: str = "English",
        overrides: dict[str, Any] | None = None,
    ) -> str:
        """Generate an empathetic, brand-aligned reply to a customer review."""
        system_prompt = (
            "You are the customer experience manager for a local business. "
            f"Write a concise, genuine, polite response (2-4 sentences) in {language} to the customer review. "
            "If the review is negative, acknowledge the concern empathetically without being defensive "
            "and invite them to reconnect directly."
        )
        user_prompt = (
            f"Business: {business.name} ({business.category})\n"
            f"Contact: {business.email or business.phone or 'our front desk'}\n"
            f"Reviewer: {review.reviewer_name}\n"
            f"Rating: {review.rating}/5 on {review.platform}\n"
            f"Review: {review.review_text or '(No written comment)'}\n"
            f"Tone: {tone}\n"
            f"Language: {language}\n"
            "Write the owner's reply:"
        )

        llm_reply = await generate_text_with_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            overrides=overrides,
            temperature=0.6,
            max_tokens=220,
        )
        if llm_reply:
            return llm_reply

        first_name = (review.reviewer_name or "there").split()[0]
        contact = business.email or business.phone or "us directly"

        if review.rating >= 4:
            return (
                f"Hi {first_name}, thank you so much for the {review.rating}-star review and kind words! "
                f"Our team at {business.name} loves making every visit memorable, and we look forward to welcoming you back soon."
            )
        if review.rating == 3:
            return (
                f"Hi {first_name}, thank you for sharing your feedback with {business.name}. "
                "We appreciate knowing what went well and where we can elevate your next visit to a true 5-star experience. "
                f"Please feel free to reach out to {contact} anytime!"
            )
        return (
            f"Hi {first_name}, thank you for bringing this to our attention, and please accept our sincere apologies "
            f"that your experience at {business.name} fell short of expectations. "
            "We take feedback like yours seriously and are reviewing it with our team. "
            f"Please reach out to {contact} so we can make this right personally."
        )
