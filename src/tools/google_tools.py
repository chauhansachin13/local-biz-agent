"""LangChain tools for managing Google Business Profile (GBP) operations.

Provides `@tool` functions and a `GoogleBusinessTools` bundle with stub/mock
implementations that log every action and return realistic GBP API responses
when live credentials are not configured.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# In-memory mock store for GBP state during a session
_MOCK_PROFILES: Dict[str, Dict[str, Any]] = {}
_MOCK_QA: Dict[str, List[Dict[str, Any]]] = {
    "default": [
        {
            "question_id": "qa_101",
            "author": "Alex M.",
            "question": "Do you offer wheelchair-accessible parking and seating?",
            "answer": None,
            "created_at": "2026-11-20T14:30:00Z",
        },
        {
            "question_id": "qa_102",
            "author": "Priya S.",
            "question": "Are walk-ins welcome on weekends or do I need a reservation?",
            "answer": "Walk-ins are always welcome, though reservations are recommended on Saturdays.",
            "created_at": "2026-11-22T09:15:00Z",
        },
    ]
}


@tool
def update_business_profile(business_data: dict) -> str:
    """Create or update a local business's Google Business Profile information.

    Args:
        business_data: Dictionary containing fields to update such as
            `location_id`, `name`, `category`, `description`, `phone`,
            `website`, `address`, and `attributes`.

    Returns:
        JSON string summarizing the updated profile status and fields modified.
    """
    location_id = str(business_data.get("location_id", f"loc_{uuid.uuid4().hex[:8]}"))
    existing = _MOCK_PROFILES.get(location_id, {})
    updated = {
        **existing,
        **business_data,
        "location_id": location_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _MOCK_PROFILES[location_id] = updated

    logger.info(
        "[GBP Stub] Updated business profile for location_id=%s fields=%s",
        location_id,
        list(business_data.keys()),
    )
    return json.dumps(
        {
            "status": "success",
            "mode": "stub",
            "location_id": location_id,
            "updated_fields": list(business_data.keys()),
            "profile": updated,
            "message": f"Google Business Profile '{location_id}' updated successfully.",
        },
        indent=2,
    )


@tool
def post_google_update(
    location_id: str, content: str, image_url: Optional[str] = None
) -> str:
    """Publish a local update/post to a Google Business Profile listing.

    Args:
        location_id: The Google Business Profile location identifier.
        content: Text body of the Google Business update (max ~1500 characters).
        image_url: Optional publicly accessible image URL to attach to the post.

    Returns:
        JSON string containing the created post ID, live link, and timestamp.
    """
    if not content or not content.strip():
        return json.dumps({"status": "error", "message": "Post content cannot be empty."})

    post_id = f"gbp_post_{uuid.uuid4().hex[:10]}"
    published_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "[GBP Stub] Published Google Business post_id=%s location_id=%s has_image=%s",
        post_id,
        location_id,
        bool(image_url),
    )
    return json.dumps(
        {
            "status": "published",
            "mode": "stub",
            "post_id": post_id,
            "location_id": location_id,
            "content_preview": content[:120],
            "image_url": image_url,
            "published_at": published_at,
            "post_url": f"https://business.google.com/locations/{location_id}/posts/{post_id}",
        },
        indent=2,
    )


@tool
def get_business_insights(location_id: str, days: int = 30) -> dict:
    """Retrieve Google Business Profile search, map views, and customer action insights.

    Args:
        location_id: The Google Business Profile location identifier.
        days: Number of trailing days to aggregate (default 30).

    Returns:
        Dictionary with views, search queries, calls, direction requests,
        website clicks, and period-over-period deltas.
    """
    days = max(1, min(days, 365))
    scale = days / 30.0
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    insights = {
        "status": "success",
        "mode": "stub",
        "location_id": location_id,
        "period": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "metrics": {
            "google_search_views": int(2840 * scale),
            "google_maps_views": int(4120 * scale),
            "total_profile_views": int(6960 * scale),
            "website_clicks": int(418 * scale),
            "direction_requests": int(312 * scale),
            "phone_calls": int(164 * scale),
            "photo_views": int(1950 * scale),
        },
        "growth_vs_previous_period": {
            "total_profile_views_pct": 12.4,
            "website_clicks_pct": 8.7,
            "direction_requests_pct": 15.2,
            "phone_calls_pct": 5.1,
        },
        "top_search_queries": [
            {"query": "best local coffee near me", "impressions": int(620 * scale)},
            {"query": "open now", "impressions": int(410 * scale)},
            {"query": "book appointment", "impressions": int(285 * scale)},
        ],
    }

    logger.info(
        "[GBP Stub] Fetched insights for location_id=%s days=%d total_views=%d",
        location_id,
        days,
        insights["metrics"]["total_profile_views"],
    )
    return insights


@tool
def update_business_hours(location_id: str, hours: dict) -> str:
    """Update regular or special operating hours for a Google Business Profile.

    Args:
        location_id: The Google Business Profile location identifier.
        hours: Mapping of weekday names (e.g. `monday`, `tuesday`) or special
            dates to opening/closing windows (e.g. `{"open": "09:00", "close": "18:00"}`
            or `"closed"`).

    Returns:
        JSON string confirming the updated schedule.
    """
    profile = _MOCK_PROFILES.setdefault(location_id, {"location_id": location_id})
    profile["hours"] = hours
    profile["hours_updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(
        "[GBP Stub] Updated operating hours for location_id=%s days=%s",
        location_id,
        list(hours.keys()),
    )
    return json.dumps(
        {
            "status": "success",
            "mode": "stub",
            "location_id": location_id,
            "hours": hours,
            "updated_at": profile["hours_updated_at"],
            "message": f"Operating hours updated for location '{location_id}'.",
        },
        indent=2,
    )


@tool
def manage_business_photos(
    location_id: str,
    action: str,
    photo_url: Optional[str] = None,
    category: str = "ADDITIONAL",
) -> str:
    """Add, list, or remove photos on a Google Business Profile listing.

    Args:
        location_id: The Google Business Profile location identifier.
        action: One of `'add'`, `'list'`, or `'remove'`.
        photo_url: URL of the photo to add or remove (required for add/remove).
        category: GBP photo category (`COVER`, `LOGO`, `INTERIOR`, `EXTERIOR`, `ADDITIONAL`).

    Returns:
        JSON string with photo operation result.
    """
    profile = _MOCK_PROFILES.setdefault(location_id, {"location_id": location_id, "photos": []})
    photos: List[Dict[str, Any]] = profile.setdefault("photos", [])
    normalized_action = action.strip().lower()

    if normalized_action == "list":
        logger.info("[GBP Stub] Listed %d photos for location_id=%s", len(photos), location_id)
        return json.dumps({"status": "success", "location_id": location_id, "photos": photos}, indent=2)

    if not photo_url:
        return json.dumps({"status": "error", "message": "photo_url is required for add/remove."})

    if normalized_action == "add":
        entry = {
            "photo_id": f"gbp_photo_{uuid.uuid4().hex[:8]}",
            "url": photo_url,
            "category": category.upper(),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        photos.append(entry)
        logger.info("[GBP Stub] Added photo to location_id=%s category=%s", location_id, category)
        return json.dumps({"status": "added", "location_id": location_id, "photo": entry}, indent=2)

    if normalized_action == "remove":
        before = len(photos)
        profile["photos"] = [p for p in photos if p.get("url") != photo_url]
        removed = before - len(profile["photos"])
        logger.info("[GBP Stub] Removed %d photo(s) from location_id=%s", removed, location_id)
        return json.dumps({"status": "removed", "location_id": location_id, "removed_count": removed}, indent=2)

    return json.dumps({"status": "error", "message": f"Unsupported action '{action}'."})


@tool
def handle_business_qa(
    location_id: str,
    action: str = "list",
    question_id: Optional[str] = None,
    answer_text: Optional[str] = None,
) -> str:
    """List customer Q&A entries or post an official owner answer on Google Business Profile.

    Args:
        location_id: The Google Business Profile location identifier.
        action: Either `'list'` to fetch Q&A items or `'answer'` to reply to a question.
        question_id: Question ID to answer when `action='answer'`.
        answer_text: Official business response when `action='answer'`.

    Returns:
        JSON string containing Q&A items or answer confirmation.
    """
    items = _MOCK_QA.setdefault(location_id, [dict(q) for q in _MOCK_QA["default"]])
    if action.strip().lower() == "list":
        logger.info("[GBP Stub] Fetched %d Q&A entries for location_id=%s", len(items), location_id)
        return json.dumps({"status": "success", "location_id": location_id, "questions": items}, indent=2)

    if action.strip().lower() == "answer":
        if not question_id or not answer_text:
            return json.dumps(
                {"status": "error", "message": "Both question_id and answer_text are required."}
            )
        for item in items:
            if item["question_id"] == question_id:
                item["answer"] = answer_text
                item["answered_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "[GBP Stub] Answered Q&A question_id=%s on location_id=%s",
                    question_id,
                    location_id,
                )
                return json.dumps({"status": "answered", "location_id": location_id, "item": item}, indent=2)
        return json.dumps({"status": "error", "message": f"Question '{question_id}' not found."})

    return json.dumps({"status": "error", "message": f"Unsupported action '{action}'."})


class GoogleBusinessTools:
    """Collection wrapper for Google Business Profile LangChain tools."""

    update_business_profile = update_business_profile
    post_google_update = post_google_update
    get_business_insights = get_business_insights
    update_business_hours = update_business_hours
    manage_business_photos = manage_business_photos
    handle_business_qa = handle_business_qa

    @classmethod
    def get_tools(cls) -> list:
        """Return all Google Business Profile tools as a list."""
        return [
            update_business_profile,
            post_google_update,
            get_business_insights,
            update_business_hours,
            manage_business_photos,
            handle_business_qa,
        ]
