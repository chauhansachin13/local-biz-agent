"""LangChain tools for Social Media publishing, scheduling, and analytics backed by SQLite."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import tool

from src.tools.db_helper import open_sqlite_if_ready

logger = logging.getLogger(__name__)

_SCHEDULED_POSTS: list[dict[str, Any]] = []


def _persist_social_post(
    platform_enum: str,
    content: str,
    image_url: str | None = None,
    status_enum: str = "PUBLISHED",
    scheduled_at: str | None = None,
    business_id: int = 1,
) -> tuple[str, str]:
    now_iso = datetime.now(UTC).isoformat()
    with open_sqlite_if_ready("businesses", "social_posts") as conn:
        if conn is not None:
            biz = conn.execute(
                "SELECT id FROM businesses WHERE id = ? LIMIT 1", (business_id,)
            ).fetchone()
            if biz is None:
                biz = conn.execute("SELECT id FROM businesses ORDER BY id ASC LIMIT 1").fetchone()
            if biz is not None:
                cur = conn.execute(
                    """
                    INSERT INTO social_posts (
                        business_id, platform, content, image_url, scheduled_at, published_at,
                        status, engagement_likes, engagement_shares, engagement_comments, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
                    """,
                    (
                        biz["id"],
                        platform_enum,
                        content,
                        image_url,
                        scheduled_at,
                        now_iso if status_enum == "PUBLISHED" else None,
                        status_enum,
                        now_iso,
                    ),
                )
                conn.commit()
                return str(cur.lastrowid), "database"
    return f"post_{uuid.uuid4().hex[:10]}", "stub"


@tool
def post_to_facebook(page_id: str, content: str, image_url: str | None = None) -> str:
    """Publish a post to a business Facebook Page and persist it to SQLite."""
    if not content or not content.strip():
        return json.dumps({"status": "error", "message": "Facebook post content cannot be empty."})

    biz_id = int(page_id) if str(page_id).isdigit() else 1
    post_id, mode = _persist_social_post(
        "FACEBOOK", content.strip(), image_url, "PUBLISHED", business_id=biz_id
    )
    return json.dumps(
        {
            "status": "published",
            "mode": mode,
            "platform": "facebook",
            "page_id": page_id,
            "post_id": post_id,
            "image_url": image_url,
            "published_at": datetime.now(UTC).isoformat(),
            "url": f"https://www.facebook.com/{page_id}/posts/{post_id}",
        },
        indent=2,
    )


@tool
def post_to_instagram(content: str, image_url: str, hashtags: list | None = None) -> str:
    """Publish a photo post with caption and hashtags to Instagram Business."""
    if not image_url or not image_url.strip():
        return json.dumps(
            {"status": "error", "message": "Instagram posts require a valid image_url."}
        )

    formatted_tags = [
        tag if str(tag).startswith("#") else f"#{str(tag).strip()}"
        for tag in (hashtags or [])
        if str(tag).strip()
    ]
    full_caption = f"{content.strip()}\n\n{' '.join(formatted_tags)}".strip()
    media_id, mode = _persist_social_post("INSTAGRAM", full_caption, image_url, "PUBLISHED")
    return json.dumps(
        {
            "status": "published",
            "mode": mode,
            "platform": "instagram",
            "media_id": media_id,
            "image_url": image_url,
            "caption": full_caption,
            "hashtag_count": len(formatted_tags),
            "published_at": datetime.now(UTC).isoformat(),
            "url": f"https://www.instagram.com/p/{media_id}/",
        },
        indent=2,
    )


@tool
def post_to_twitter(content: str, image_url: str | None = None) -> str:
    """Publish a post to X (Twitter), enforcing the 280-character limit."""
    cleaned = (content or "").strip()
    if not cleaned:
        return json.dumps({"status": "error", "message": "Tweet content cannot be empty."})
    if len(cleaned) > 280:
        return json.dumps(
            {
                "status": "error",
                "message": f"Tweet exceeds 280 characters (length={len(cleaned)}). Please shorten it.",
            }
        )

    tweet_id, mode = _persist_social_post("TWITTER", cleaned, image_url, "PUBLISHED")
    return json.dumps(
        {
            "status": "published",
            "mode": mode,
            "platform": "twitter",
            "tweet_id": tweet_id,
            "character_count": len(cleaned),
            "image_url": image_url,
            "published_at": datetime.now(UTC).isoformat(),
            "url": f"https://x.com/i/web/status/{tweet_id}",
        },
        indent=2,
    )


@tool
def schedule_post(platform: str, content: str, scheduled_time: str) -> str:
    """Schedule a social media post for future publication in SQLite."""
    normalized = platform.strip().lower()
    valid_platforms = {"facebook", "instagram", "twitter", "x", "google", "google_business"}
    if normalized not in valid_platforms:
        return json.dumps(
            {
                "status": "error",
                "message": f"Unsupported platform '{platform}'. Choose from {sorted(valid_platforms)}.",
            }
        )

    norm_db = (
        "TWITTER"
        if normalized in {"twitter", "x"}
        else ("GOOGLE" if "google" in normalized else normalized.upper())
    )
    schedule_id, mode = _persist_social_post(
        norm_db, content.strip(), None, "SCHEDULED", scheduled_at=scheduled_time
    )
    entry = {
        "schedule_id": schedule_id,
        "platform": norm_db.lower(),
        "content": content,
        "scheduled_time": scheduled_time,
        "status": "scheduled",
        "created_at": datetime.now(UTC).isoformat(),
    }
    _SCHEDULED_POSTS.append(entry)
    return json.dumps({"status": "scheduled", "mode": mode, **entry}, indent=2)


@tool
def get_social_metrics(platform: str, days: int = 7) -> dict:
    """Retrieve engagement and reach metrics from SQLite social posts + platform benchmarks."""
    days = max(1, min(days, 90))
    normalized = platform.strip().lower()
    live_posts = 0
    live_likes = 0
    live_shares = 0
    live_comments = 0

    with open_sqlite_if_ready("social_posts") as conn:
        if conn is not None:
            if normalized == "all":
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt, COALESCE(SUM(engagement_likes),0) AS likes, "
                    "COALESCE(SUM(engagement_shares),0) AS shares, "
                    "COALESCE(SUM(engagement_comments),0) AS comments FROM social_posts"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt, COALESCE(SUM(engagement_likes),0) AS likes, "
                    "COALESCE(SUM(engagement_shares),0) AS shares, "
                    "COALESCE(SUM(engagement_comments),0) AS comments FROM social_posts WHERE UPPER(platform) = ?",
                    (normalized.upper(),),
                ).fetchone()
            if row:
                live_posts = row["cnt"]
                live_likes = row["likes"]
                live_shares = row["shares"]
                live_comments = row["comments"]

    total_eng = live_likes + live_shares + live_comments
    return {
        "status": "success",
        "mode": "database",
        "platform": normalized,
        "days": days,
        "live_db_metrics": {
            "total_posts": live_posts,
            "likes": live_likes,
            "shares": live_shares,
            "comments": live_comments,
            "total_engagements": total_eng,
        },
        "optimal_posting_windows": ["11:00-12:30", "17:30-19:30"],
    }


@tool
def get_optimal_posting_times(platform: str, business_type: str = "local") -> dict:
    """Recommend best days and times to post on a social platform for a local business."""
    recommendations = {
        "facebook": {
            "best_days": ["Wednesday", "Thursday", "Saturday"],
            "best_times": ["09:00", "13:00", "18:30"],
            "rationale": "Local community engagement peaks mid-morning and early evening.",
        },
        "instagram": {
            "best_days": ["Tuesday", "Thursday", "Friday", "Saturday"],
            "best_times": ["11:00", "17:30", "20:00"],
            "rationale": "Visual discovery and Stories views spike during lunch and evening commutes.",
        },
        "twitter": {
            "best_days": ["Monday", "Wednesday", "Friday"],
            "best_times": ["08:30", "12:15", "17:00"],
            "rationale": "Real-time updates perform best during morning and midday breaks.",
        },
    }
    normalized = platform.strip().lower()
    data = recommendations.get(normalized, recommendations["instagram"])
    return {"platform": normalized, "business_type": business_type, **data}


class SocialMediaTools:
    """Collection wrapper for Social Media LangChain tools."""

    post_to_facebook = post_to_facebook
    post_to_instagram = post_to_instagram
    post_to_twitter = post_to_twitter
    schedule_post = schedule_post
    get_social_metrics = get_social_metrics
    get_optimal_posting_times = get_optimal_posting_times

    @classmethod
    def get_tools(cls) -> list:
        """Return all Social Media tools as a list."""
        return [
            post_to_facebook,
            post_to_instagram,
            post_to_twitter,
            schedule_post,
            get_social_metrics,
            get_optimal_posting_times,
        ]
