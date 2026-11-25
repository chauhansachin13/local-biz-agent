"""LangChain tools for customer review monitoring, sentiment analysis, and response backed by SQLite."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import tool

from src.tools.db_helper import open_sqlite_if_ready

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

_FLAGGED_REVIEWS: list[dict[str, Any]] = []
_REVIEW_RESPONSES: dict[str, dict[str, Any]] = {}


def _fetch_platform_reviews_from_db(platform: str, limit: int) -> list[dict[str, Any]] | None:
    with open_sqlite_if_ready("reviews") as conn:
        if conn is None:
            return None
        rows = conn.execute(
            """
            SELECT id, business_id, platform, reviewer_name, rating, review_text,
                   response_text, response_status, sentiment, created_at
            FROM reviews
            WHERE LOWER(platform) = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (platform.lower(), max(1, limit)),
        ).fetchall()
        if not rows:
            return None
        return [
            {
                "review_id": str(r["id"]),
                "business_id": r["business_id"],
                "platform": r["platform"],
                "author": r["reviewer_name"],
                "rating": r["rating"],
                "text": r["review_text"] or "",
                "replied": str(r["response_status"]).upper() == "RESPONDED",
                "reply": r["response_text"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


@tool
def fetch_google_reviews(location_id: str, limit: int = 20) -> list:
    """Fetch recent customer reviews from Google (from SQLite DB if present, else fallback)."""
    db_rows = _fetch_platform_reviews_from_db("google", limit)
    if db_rows is not None:
        return db_rows
    return [
        {
            "review_id": "g_rev_101",
            "platform": "google",
            "location_id": location_id,
            "author": "Sarah Jenkins",
            "rating": 5,
            "text": "Absolutely wonderful experience! Staff was friendly and fast.",
            "created_at": "2026-11-24T16:20:00Z",
            "replied": False,
        }
    ][: max(1, limit)]


@tool
def fetch_facebook_reviews(page_id: str, limit: int = 20) -> list:
    """Fetch recent customer recommendations and reviews from Facebook (SQLite DB if present)."""
    db_rows = _fetch_platform_reviews_from_db("facebook", limit)
    if db_rows is not None:
        return db_rows
    return [
        {
            "review_id": "fb_rev_201",
            "platform": "facebook",
            "page_id": page_id,
            "author": "Hannah Lopez",
            "rating": 5,
            "text": "Love this place! Consistently great service and welcoming atmosphere.",
            "created_at": "2026-11-24T12:00:00Z",
            "replied": False,
        }
    ][: max(1, limit)]


@tool
def respond_to_review(platform: str, review_id: str, response: str) -> str:
    """Post an official business reply to a customer review and persist in SQLite if matched."""
    if not response or not response.strip():
        return json.dumps({"status": "error", "message": "Review response text cannot be empty."})

    now_iso = datetime.now(UTC).isoformat()
    mode = "stub"
    if str(review_id).isdigit():
        with open_sqlite_if_ready("reviews") as conn:
            if conn is not None:
                row = conn.execute(
                    "SELECT id FROM reviews WHERE id = ?", (int(review_id),)
                ).fetchone()
                if row is not None:
                    conn.execute(
                        "UPDATE reviews SET response_text = ?, response_status = 'RESPONDED', responded_at = ? WHERE id = ?",
                        (response.strip(), now_iso, int(review_id)),
                    )
                    conn.commit()
                    mode = "database"

    record = {
        "status": "published",
        "mode": mode,
        "platform": platform.strip().lower(),
        "review_id": review_id,
        "response": response.strip(),
        "responded_at": now_iso,
    }
    _REVIEW_RESPONSES[review_id] = record
    return json.dumps(record, indent=2)


@tool
def analyze_review_sentiment(review_text: str) -> dict:
    """Analyze the sentiment, urgency, and escalation risk of a customer review."""
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

    return {
        "sentiment": sentiment,
        "score": round(raw_score, 3),
        "positive_signals": pos_hits,
        "negative_signals": neg_hits,
        "critical_triggers": critical_hits,
        "requires_escalation": requires_escalation,
        "recommended_action": recommended_action,
    }


@tool
def flag_critical_review(platform: str, review_id: str, reason: str, severity: str = "high") -> str:
    """Flag a critical negative review in SQLite (`FLAGGED`) and escalation log."""
    if str(review_id).isdigit():
        with open_sqlite_if_ready("reviews") as conn:
            if conn is not None:
                conn.execute(
                    "UPDATE reviews SET response_status = 'FLAGGED' WHERE id = ? AND response_status = 'PENDING'",
                    (int(review_id),),
                )
                conn.commit()

    ticket = {
        "status": "flagged",
        "platform": platform.strip().lower(),
        "review_id": review_id,
        "severity": severity.strip().lower(),
        "reason": reason,
        "flagged_at": datetime.now(UTC).isoformat(),
    }
    _FLAGGED_REVIEWS.append(ticket)
    logger.warning("[Review Escalation] Flagged review_id=%s reason=%s", review_id, reason)
    return json.dumps(ticket, indent=2)


@tool
def get_review_trends(business_id: str, days: int = 30) -> dict:
    """Summarize review volume, average rating, response rate, and sentiment from SQLite."""
    biz_int = int(business_id) if str(business_id).isdigit() else 1
    with open_sqlite_if_ready("reviews") as conn:
        if conn is not None:
            rows = conn.execute(
                "SELECT rating, sentiment, response_status FROM reviews WHERE business_id = ?",
                (biz_int,),
            ).fetchall()
            if rows:
                total = len(rows)
                avg = round(sum(r["rating"] for r in rows) / total, 2)
                responded = sum(1 for r in rows if str(r["response_status"]).upper() == "RESPONDED")
                pos = sum(1 for r in rows if str(r["sentiment"]).upper() == "POSITIVE")
                neu = sum(1 for r in rows if str(r["sentiment"]).upper() == "NEUTRAL")
                neg = sum(1 for r in rows if str(r["sentiment"]).upper() == "NEGATIVE")
                return {
                    "business_id": str(business_id),
                    "days": days,
                    "average_rating": avg,
                    "total_reviews": total,
                    "response_rate_pct": round((responded / total) * 100, 1),
                    "sentiment_breakdown": {"positive": pos, "neutral": neu, "negative": neg},
                }

    return {
        "business_id": str(business_id),
        "days": days,
        "average_rating": 4.3,
        "total_reviews": 0,
        "response_rate_pct": 0.0,
        "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
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
