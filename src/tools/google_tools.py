"""LangChain tools for managing Google Business Profile (GBP) operations backed by SQLite.

Persists profile updates, GBP posts, and hours directly into the local SQLite database
when a matching business exists, while supporting standalone mock/stub execution.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.tools import tool

from src.tools.db_helper import open_sqlite_if_ready

logger = logging.getLogger(__name__)

_MOCK_PROFILES: dict[str, dict[str, Any]] = {}
_MOCK_QA: dict[str, list[dict[str, Any]]] = {
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


def _find_business_row(conn, location_id: str, business_id: Any = None):
    if business_id is not None and str(business_id).isdigit():
        row = conn.execute("SELECT * FROM businesses WHERE id = ?", (int(business_id),)).fetchone()
        if row:
            return row
    if location_id:
        row = conn.execute(
            "SELECT * FROM businesses WHERE google_business_id = ?", (location_id,)
        ).fetchone()
        if row:
            return row
        if location_id.startswith("loc_") and location_id[4:].isdigit():
            return conn.execute(
                "SELECT * FROM businesses WHERE id = ?", (int(location_id[4:]),)
            ).fetchone()
    return None


@tool
def update_business_profile(business_data: dict) -> str:
    """Create or update a local business's Google Business Profile information.

    Args:
        business_data: Dictionary containing fields to update such as `business_id`,
            `location_id`, `name`, `category`, `description`, `phone`, `website`, `address`.

    Returns:
        JSON string summarizing the updated profile status and fields modified.
    """
    location_id = str(business_data.get("location_id") or f"loc_{uuid.uuid4().hex[:8]}")
    now_iso = datetime.now(UTC).isoformat()
    mode = "stub"

    with open_sqlite_if_ready("businesses") as conn:
        if conn is not None:
            row = _find_business_row(conn, location_id, business_data.get("business_id"))
            if row is not None:
                allowed = (
                    "name",
                    "category",
                    "description",
                    "phone",
                    "website",
                    "address",
                    "city",
                    "state",
                )
                updates = {
                    k: business_data[k]
                    for k in allowed
                    if k in business_data and business_data[k] is not None
                }
                if updates:
                    set_clause = ", ".join(f"{col} = ?" for col in updates)
                    params = [*updates.values(), now_iso, row["id"]]
                    conn.execute(
                        f"UPDATE businesses SET {set_clause}, updated_at = ? WHERE id = ?",
                        params,
                    )
                    conn.commit()
                mode = "database"

    existing = _MOCK_PROFILES.get(location_id, {})
    updated = {**existing, **business_data, "location_id": location_id, "updated_at": now_iso}
    _MOCK_PROFILES[location_id] = updated

    logger.info("[GBP %s] Updated profile location_id=%s", mode, location_id)
    return json.dumps(
        {
            "status": "success",
            "mode": mode,
            "location_id": location_id,
            "updated_fields": list(business_data.keys()),
            "profile": updated,
            "message": f"Google Business Profile '{location_id}' updated successfully.",
        },
        indent=2,
    )


@tool
def post_google_update(location_id: str, content: str, image_url: str | None = None) -> str:
    """Publish a local update/post to a Google Business Profile listing and persist to SQLite.

    Args:
        location_id: The Google Business Profile location identifier.
        content: Text body of the Google Business update.
        image_url: Optional publicly accessible image URL.

    Returns:
        JSON string containing the created post ID, live link, and timestamp.
    """
    if not content or not content.strip():
        return json.dumps({"status": "error", "message": "Post content cannot be empty."})

    post_id = f"gbp_post_{uuid.uuid4().hex[:10]}"
    published_at = datetime.now(UTC).isoformat()
    mode = "stub"

    with open_sqlite_if_ready("businesses", "social_posts") as conn:
        if conn is not None:
            row = _find_business_row(conn, location_id)
            if row is not None:
                cur = conn.execute(
                    """
                    INSERT INTO social_posts (
                        business_id, platform, content, image_url, published_at,
                        status, engagement_likes, engagement_shares, engagement_comments, created_at
                    ) VALUES (?, 'GOOGLE', ?, ?, ?, 'PUBLISHED', 0, 0, 0, ?)
                    """,
                    (row["id"], content.strip(), image_url, published_at, published_at),
                )
                conn.commit()
                post_id = str(cur.lastrowid)
                mode = "database"

    logger.info("[GBP %s] Published Google post_id=%s location_id=%s", mode, post_id, location_id)
    return json.dumps(
        {
            "status": "published",
            "mode": mode,
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
        Dictionary with views, search queries, calls, direction requests, and deltas.
    """
    days = max(1, min(days, 365))
    scale = days / 30.0
    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=days)

    extra_queries: list[dict[str, Any]] = []
    with open_sqlite_if_ready("businesses") as conn:
        if conn is not None:
            row = _find_business_row(conn, location_id)
            if row is not None and row["city"] and row["category"]:
                extra_queries = [
                    {
                        "query": f"best {row['category'].lower()} in {row['city']}",
                        "impressions": int(680 * scale),
                    },
                    {"query": f"{row['name']}", "impressions": int(450 * scale)},
                    {
                        "query": f"{row['category'].lower()} open now",
                        "impressions": int(310 * scale),
                    },
                ]

    metrics = {
        "google_search_views": int(2840 * scale),
        "google_maps_views": int(4120 * scale),
        "total_profile_views": int(6960 * scale),
        "website_clicks": int(418 * scale),
        "direction_requests": int(312 * scale),
        "phone_calls": int(164 * scale),
        "photo_views": int(1950 * scale),
    }

    return {
        "status": "success",
        "mode": "hybrid",
        "location_id": location_id,
        "period": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "total_views": metrics["total_profile_views"],
            "direction_requests": metrics["direction_requests"],
            "phone_calls": metrics["phone_calls"],
            "website_clicks": metrics["website_clicks"],
        },
        "metrics": metrics,
        "growth_vs_previous_period": {
            "total_profile_views_pct": 12.4,
            "website_clicks_pct": 8.7,
            "direction_requests_pct": 15.2,
            "phone_calls_pct": 5.1,
        },
        "top_search_queries": extra_queries
        or [
            {"query": "best local coffee near me", "impressions": int(620 * scale)},
            {"query": "open now", "impressions": int(410 * scale)},
            {"query": "book appointment", "impressions": int(285 * scale)},
        ],
    }


@tool
def update_business_hours(location_id: str, hours: dict) -> str:
    """Update operating hours for a Google Business Profile in SQLite.

    Args:
        location_id: The Google Business Profile location identifier.
        hours: Mapping of weekday names to opening/closing windows.

    Returns:
        JSON string confirming the updated schedule.
    """
    now_iso = datetime.now(UTC).isoformat()
    mode = "stub"
    with open_sqlite_if_ready("businesses") as conn:
        if conn is not None:
            row = _find_business_row(conn, location_id)
            if row is not None:
                conn.execute(
                    "UPDATE businesses SET operating_hours = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(hours), now_iso, row["id"]),
                )
                conn.commit()
                mode = "database"

    profile = _MOCK_PROFILES.setdefault(location_id, {"location_id": location_id})
    profile["hours"] = hours
    profile["hours_updated_at"] = now_iso

    return json.dumps(
        {
            "status": "success",
            "mode": mode,
            "location_id": location_id,
            "hours": hours,
            "updated_at": now_iso,
            "message": f"Operating hours updated for location '{location_id}'.",
        },
        indent=2,
    )


@tool
def manage_business_photos(
    location_id: str,
    action: str,
    photo_url: str | None = None,
    category: str = "ADDITIONAL",
) -> str:
    """Add, list, or remove photos on a Google Business Profile listing."""
    profile = _MOCK_PROFILES.setdefault(location_id, {"location_id": location_id, "photos": []})
    photos: list[dict[str, Any]] = profile.setdefault("photos", [])
    normalized_action = action.strip().lower()

    if normalized_action == "list":
        return json.dumps(
            {"status": "success", "location_id": location_id, "photos": photos}, indent=2
        )
    if not photo_url:
        return json.dumps({"status": "error", "message": "photo_url is required for add/remove."})
    if normalized_action == "add":
        entry = {
            "photo_id": f"gbp_photo_{uuid.uuid4().hex[:8]}",
            "url": photo_url,
            "category": category.upper(),
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
        photos.append(entry)
        return json.dumps({"status": "added", "location_id": location_id, "photo": entry}, indent=2)
    if normalized_action == "remove":
        before = len(photos)
        profile["photos"] = [p for p in photos if p.get("url") != photo_url]
        return json.dumps(
            {
                "status": "removed",
                "location_id": location_id,
                "removed_count": before - len(profile["photos"]),
            },
            indent=2,
        )
    return json.dumps({"status": "error", "message": f"Unsupported action '{action}'."})


@tool
def handle_business_qa(
    location_id: str,
    action: str = "list",
    question_id: str | None = None,
    answer_text: str | None = None,
) -> str:
    """List customer Q&A entries or post an official owner answer on Google Business Profile."""
    items = _MOCK_QA.setdefault(location_id, [dict(q) for q in _MOCK_QA["default"]])
    if action.strip().lower() == "list":
        return json.dumps(
            {"status": "success", "location_id": location_id, "questions": items}, indent=2
        )
    if action.strip().lower() == "answer":
        if not question_id or not answer_text:
            return json.dumps(
                {"status": "error", "message": "Both question_id and answer_text are required."}
            )
        for item in items:
            if item["question_id"] == question_id:
                item["answer"] = answer_text
                item["answered_at"] = datetime.now(UTC).isoformat()
                return json.dumps(
                    {"status": "answered", "location_id": location_id, "item": item}, indent=2
                )
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
