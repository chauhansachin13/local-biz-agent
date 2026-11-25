"""LangChain tools for cross-platform customer review monitoring and response.

Provides `@tool` functions and a `ReviewTools` wrapper for fetching Google and
Facebook reviews, analyzing sentiment, responding to reviews, and flagging
critical feedback for human escalation.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_POSITIVE_WORDS = {
    "amazing",
    "awesome",
    "best",
    "clean",
    "courteous",
    "delicious",
    "excellent",
    "fantastic",
    "fast",
    "friendly",
    "great",
    "helpful",
    "love",
    "loved",
    "outstanding",
    "polite",
    "professional",
    "quick",
    "recommend",
    "superb",
    "wonderful",
}

_NEGATIVE_WORDS = {
    "awful",
    "bad",
    "broken",
    "cold",
    "dirty",
    "disappointed",
    "disappointing",
    "horrible",
    "late",
    "overpriced",
    "poor",
    "rude",
    "slow",
    "terrible",
    "unacceptable",
    "unprofessional",
    "wait",
    "waited",
    "worst",
    "wrong",
}

_CRITICAL_KEYWORDS = {
    "food poisoning",
    "sick",
    "allergy",
    "unsafe",
    "harassment",
    "discrimination",
    "scam",
    "fraud",
    "refund",
    "lawyer",
    "health department",
    "injury",
}

_FLAGGED_REVIEWS: List[Dict[str, Any]] = []
_REVIEW_RESPONSES: Dict[str, Dict[str, Any]] = {}


@tool
def fetch_google_reviews(location_id: str, limit: int = 20) -> list:
    """Fetch recent customer reviews from Google Business Profile.

    Args:
        location_id: Google Business Profile location ID.
        limit: Maximum number of reviews to return (default 20).

    Returns:
        List of review dictionaries containing `review_id`, `author`, `rating`,
        `text`, `created_at`, and `replied`.
    """
    sample_reviews = [
        {
            "review_id": "g_rev_101",
            "platform": "google",
            "location_id": location_id,
            "author": "Sarah Jenkins",
            "rating": 5,
            "text": "Absolutely wonderful experience! The staff was friendly, fast, and super attentive.",
            "created_at": "2026-11-24T16:20:00Z",
            "replied": False,
        },
        {
            "review_id": "g_rev_102",
            "platform": "google",
            "location_id": location_id,
            "author": "Marcus Vance",
            "rating": 2,
            "text": "Waited 40 minutes past my scheduled time and the front desk seemed overwhelmed and rude.",
            "created_at": "2026-11-23T19:05:00Z",
            "replied": False,
        },
        {
            "review_id": "g_rev_103",
            "platform": "google",
            "location_id": location_id,
            "author": "Elena Rostova",
            "rating": 4,
            "text": "Great quality and clean space. Parking was a little tight, otherwise fantastic.",
            "created_at": "2026-11-21T11:45:00Z",
            "replied": True,
        },
        {
            "review_id": "g_rev_104",
            "platform": "google",
            "location_id": location_id,
            "author": "David Kim",
            "rating": 1,
            "text": "Unacceptable billing mistake and no one called back about my refund request.",
            "created_at": "2026-11-20T09:10:00Z",
            "replied": False,
        },
    ]
    results = sample_reviews[: max(1, limit)]
    for rev in results:
        if rev["review_id"] in _REVIEW_RESPONSES:
            rev["replied"] = True
            rev["reply"] = _REVIEW_RESPONSES[rev["review_id"]]["response"]

    logger.info(
        "[Review Stub] Fetched %d Google reviews for location_id=%s",
        len(results),
        location_id,
    )
    return results


@tool
def fetch_facebook_reviews(page_id: str, limit: int = 20) -> list:
    """Fetch recent customer recommendations and reviews from a Facebook Page.

    Args:
        page_id: Facebook Page ID.
        limit: Maximum number of reviews to return (default 20).

    Returns:
        List of Facebook review dictionaries.
    """
    sample_reviews = [
        {
            "review_id": "fb_rev_201",
            "platform": "facebook",
            "page_id": page_id,
            "author": "Hannah Lopez",
            "rating": 5,
            "recommendation_type": "positive",
            "text": "Love this place! Consistently great service and welcoming atmosphere.",
            "created_at": "2026-11-24T12:00:00Z",
            "replied": False,
        },
        {
            "review_id": "fb_rev_202",
            "platform": "facebook",
            "page_id": page_id,
            "author": "Trevor Patel",
            "rating": 3,
            "recommendation_type": "neutral",
            "text": "Service was polite and clean, though prices felt slightly high for what was included.",
            "created_at": "2026-11-19T15:30:00Z",
            "replied": False,
        },
    ]
    results = sample_reviews[: max(1, limit)]
    for rev in results:
        if rev["review_id"] in _REVIEW_RESPONSES:
            rev["replied"] = True
            rev["reply"] = _REVIEW_RESPONSES[rev["review_id"]]["response"]

    logger.info(
        "[Review Stub] Fetched %d Facebook reviews for page_id=%s",
        len(results),
        page_id,
    )
    return results


@tool
def respond_to_review(platform: str, review_id: str, response: str) -> str:
    """Post an official business reply to a customer review on Google or Facebook.

    Args:
        platform: Review platform (`google` or `facebook`).
        review_id: Unique review identifier.
        response: Reply message written on behalf of the business.

    Returns:
        JSON string confirming reply publication.
    """
    if not response or not response.strip():
        return json.dumps({"status": "error", "message": "Review response text cannot be empty."})

    record = {
        "status": "published",
        "mode": "stub",
        "platform": platform.strip().lower(),
        "review_id": review_id,
        "response": response.strip(),
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }
    _REVIEW_RESPONSES[review_id] = record

    logger.info(
        "[Review Stub] Posted reply to platform=%s review_id=%s",
        record["platform"],
        review_id,
    )
    return json.dumps(record, indent=2)


@tool
def analyze_review_sentiment(review_text: str) -> dict:
    """Analyze the sentiment, urgency, and escalation risk of a customer review.

    Args:
        review_text: Raw review body text.

    Returns:
        Dictionary with `sentiment` (`positive`, `neutral`, or `negative`),
        `score` (-1.0 to 1.0), `requires_escalation` (bool), `matched_themes`,
        and `recommended_action`.
    """
    normalized = (review_text or "").lower()
    tokens = set(re.findall(r"[a-z']+", normalized))

    pos_hits = sorted(tokens & _POSITIVE_WORDS)
    neg_hits = sorted(tokens & _NEGATIVE_WORDS)
    critical_hits = sorted(kw for kw in _CRITICAL_KEYWORDS if kw in normalized)

    total_hits = len(pos_hits) + len(neg_hits)
    raw_score = (len(pos_hits) - len(neg_hits)) / total_hits if total_hits else 0.0
    if critical_hits:
        raw_score = min(raw_score, -0.75)

    if raw_score >= 0.2:
        sentiment = "positive"
    elif raw_score <= -0.2:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    requires_escalation = bool(critical_hits) or (sentiment == "negative" and len(neg_hits) >= 2)
    recommended_action = (
        "Escalate immediately to owner/manager and respond empathetically offline + publicly."
        if requires_escalation
        else (
            "Respond warmly and thank the customer."
            if sentiment == "positive"
            else "Acknowledge feedback professionally and invite follow-up."
        )
    )

    result = {
        "sentiment": sentiment,
        "score": round(raw_score, 3),
        "positive_signals": pos_hits,
        "negative_signals": neg_hits,
        "critical_triggers": critical_hits,
        "requires_escalation": requires_escalation,
        "recommended_action": recommended_action,
    }
    logger.info(
        "[Review] Sentiment analyzed: sentiment=%s score=%.3f escalate=%s",
        sentiment,
        result["score"],
        requires_escalation,
    )
    return result


@tool
def flag_critical_review(
    platform: str, review_id: str, reason: str, severity: str = "high"
) -> str:
    """Flag a critical negative review for immediate human manager attention.

    Args:
        platform: Platform where the review was posted (`google` or `facebook`).
        review_id: Unique review identifier.
        reason: Explanation of why human escalation is needed.
        severity: Escalation severity (`medium`, `high`, or `critical`).

    Returns:
        JSON string confirming the escalation ticket.
    """
    ticket = {
        "status": "flagged",
        "platform": platform.strip().lower(),
        "review_id": review_id,
        "severity": severity.strip().lower(),
        "reason": reason,
        "flagged_at": datetime.now(timezone.utc).isoformat(),
    }
    _FLAGGED_REVIEWS.append(ticket)
    logger.warning(
        "[Review Escalation] Flagged review_id=%s platform=%s severity=%s reason=%s",
        review_id,
        ticket["platform"],
        ticket["severity"],
        reason,
    )
    return json.dumps(ticket, indent=2)


@tool
def get_review_trends(business_id: str, days: int = 30) -> dict:
    """Summarize review volume, average rating, response rate, and sentiment trends.

    Args:
        business_id: Local business identifier.
        days: Trailing time window in days (default 30).

    Returns:
        Dictionary of review KPIs and recurring customer themes.
    """
    logger.info("[Review Stub] Calculated review trends for business_id=%s days=%d", business_id, days)
    return {
        "business_id": str(business_id),
        "days": days,
        "average_rating": 4.3,
        "rating_delta": 0.2,
        "total_reviews": 28,
        "response_rate_pct": 85.7,
        "sentiment_breakdown": {"positive": 21, "neutral": 4, "negative": 3},
        "top_praised_themes": ["friendly staff", "cleanliness", "service quality"],
        "top_improvement_areas": ["wait times during peak hours", "parking clarity", "billing follow-up"],
    }


class ReviewTools:
    """Collection wrapper for Review Management LangChain tools."""

    fetch_google_reviews = fetch_google_reviews
    fetch_facebook_reviews = fetch_facebook_reviews
    respond_to_review = respond_to_review
    analyze_review_sentiment = analyze_review_sentiment
    flag_critical_review = flag_critical_review
    get_review_trends = get_review_trends

    @classmethod
    def get_tools(cls) -> list:
        """Return all Review Management tools as a list."""
        return [
            fetch_google_reviews,
            fetch_facebook_reviews,
            respond_to_review,
            analyze_review_sentiment,
            flag_critical_review,
            get_review_trends,
        ]
