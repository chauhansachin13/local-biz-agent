"""LangChain tools for Social Media publishing, scheduling, and analytics.

Provides `@tool` functions and a `SocialMediaTools` wrapper supporting Facebook,
Instagram, and Twitter/X with stub implementations that validate platform
constraints and log all actions.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_SCHEDULED_POSTS: List[Dict[str, Any]] = []


@tool
def post_to_facebook(
    page_id: str, content: str, image_url: Optional[str] = None
) -> str:
    """Publish a post to a business Facebook Page.

    Args:
        page_id: The Facebook Page ID.
        content: Text copy for the Facebook post.
        image_url: Optional image URL to include with the post.

    Returns:
        JSON string with the created Facebook post ID and permalink.
    """
    if not content or not content.strip():
        return json.dumps({"status": "error", "message": "Facebook post content cannot be empty."})

    post_id = f"{page_id}_{uuid.uuid4().hex[:10]}"
    logger.info(
        "[Social Stub] Posted to Facebook page_id=%s post_id=%s has_image=%s",
        page_id,
        post_id,
        bool(image_url),
    )
    return json.dumps(
        {
            "status": "published",
            "mode": "stub",
            "platform": "facebook",
            "page_id": page_id,
            "post_id": post_id,
            "image_url": image_url,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "url": f"https://www.facebook.com/{page_id}/posts/{post_id}",
        },
        indent=2,
    )


@tool
def post_to_instagram(
    content: str, image_url: str, hashtags: Optional[list] = None
) -> str:
    """Publish a photo post with caption and hashtags to Instagram Business.

    Args:
        content: Caption text for the Instagram post.
        image_url: Publicly accessible image URL (required for Instagram feed posts).
        hashtags: Optional list of hashtag strings (with or without leading `#`).

    Returns:
        JSON string with the published media ID, formatted caption, and permalink.
    """
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
    media_id = f"ig_{uuid.uuid4().hex[:12]}"

    logger.info(
        "[Social Stub] Posted to Instagram media_id=%s hashtags=%d",
        media_id,
        len(formatted_tags),
    )
    return json.dumps(
        {
            "status": "published",
            "mode": "stub",
            "platform": "instagram",
            "media_id": media_id,
            "image_url": image_url,
            "caption": full_caption,
            "hashtag_count": len(formatted_tags),
            "published_at": datetime.now(timezone.utc).isoformat(),
            "url": f"https://www.instagram.com/p/{media_id}/",
        },
        indent=2,
    )


@tool
def post_to_twitter(content: str, image_url: Optional[str] = None) -> str:
    """Publish a post to X (Twitter), enforcing the 280-character limit.

    Args:
        content: Tweet text (must be 280 characters or fewer).
        image_url: Optional image URL to attach.

    Returns:
        JSON string with the created tweet ID and URL, or validation error.
    """
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

    tweet_id = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    logger.info(
        "[Social Stub] Posted to Twitter/X tweet_id=%s chars=%d has_image=%s",
        tweet_id,
        len(cleaned),
        bool(image_url),
    )
    return json.dumps(
        {
            "status": "published",
            "mode": "stub",
            "platform": "twitter",
            "tweet_id": tweet_id,
            "character_count": len(cleaned),
            "image_url": image_url,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "url": f"https://x.com/i/web/status/{tweet_id}",
        },
        indent=2,
    )


@tool
def schedule_post(platform: str, content: str, scheduled_time: str) -> str:
    """Schedule a social media post for future publication.

    Args:
        platform: Target platform (`facebook`, `instagram`, `twitter`, or `google_business`).
        content: Post copy to publish.
        scheduled_time: ISO-8601 timestamp string (e.g. `2026-11-28T10:30:00Z`).

    Returns:
        JSON string confirming the scheduled job ID and execution time.
    """
    normalized = platform.strip().lower()
    valid_platforms = {"facebook", "instagram", "twitter", "x", "google_business"}
    if normalized not in valid_platforms:
        return json.dumps(
            {
                "status": "error",
                "message": f"Unsupported platform '{platform}'. Choose from {sorted(valid_platforms)}.",
            }
        )

    schedule_id = f"sched_{uuid.uuid4().hex[:10]}"
    entry = {
        "schedule_id": schedule_id,
        "platform": "twitter" if normalized == "x" else normalized,
        "content": content,
        "scheduled_time": scheduled_time,
        "status": "scheduled",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _SCHEDULED_POSTS.append(entry)

    logger.info(
        "[Social Stub] Scheduled post_id=%s platform=%s for %s",
        schedule_id,
        entry["platform"],
        scheduled_time,
    )
    return json.dumps({"status": "scheduled", "mode": "stub", **entry}, indent=2)


@tool
def get_social_metrics(platform: str, days: int = 7) -> dict:
    """Retrieve engagement and reach metrics for a social media platform.

    Args:
        platform: Platform name (`facebook`, `instagram`, `twitter`, or `all`).
        days: Number of trailing days to summarize (default 7).

    Returns:
        Dictionary of impressions, reach, engagement rate, follower growth, and top posts.
    """
    days = max(1, min(days, 90))
    scale = days / 7.0
    normalized = platform.strip().lower()

    platform_baselines = {
        "facebook": {"impressions": 3420, "engagements": 245, "clicks": 94, "followers_gained": 18},
        "instagram": {"impressions": 5180, "engagements": 490, "clicks": 132, "followers_gained": 42},
        "twitter": {"impressions": 1950, "engagements": 118, "clicks": 51, "followers_gained": 11},
    }

    if normalized == "all":
        breakdown = {}
        totals = {"impressions": 0, "engagements": 0, "clicks": 0, "followers_gained": 0}
        for name, base in platform_baselines.items():
            scaled = {k: int(v * scale) for k, v in base.items()}
            scaled["engagement_rate_pct"] = round(
                (scaled["engagements"] / max(scaled["impressions"], 1)) * 100, 2
            )
            breakdown[name] = scaled
            for k in totals:
                totals[k] += scaled[k]
        totals["engagement_rate_pct"] = round(
            (totals["engagements"] / max(totals["impressions"], 1)) * 100, 2
        )
        result: Dict[str, Any] = {
            "status": "success",
            "mode": "stub",
            "platform": "all",
            "days": days,
            "totals": totals,
            "by_platform": breakdown,
        }
    else:
        base = platform_baselines.get(
            normalized, {"impressions": 2200, "engagements": 175, "clicks": 60, "followers_gained": 14}
        )
        metrics = {k: int(v * scale) for k, v in base.items()}
        metrics["engagement_rate_pct"] = round(
            (metrics["engagements"] / max(metrics["impressions"], 1)) * 100, 2
        )
        result = {
            "status": "success",
            "mode": "stub",
            "platform": normalized,
            "days": days,
            "metrics": metrics,
            "optimal_posting_windows": ["09:00-11:00", "17:30-19:30"],
        }

    logger.info("[Social Stub] Retrieved metrics for platform=%s days=%d", normalized, days)
    return result


@tool
def get_optimal_posting_times(platform: str, business_type: str = "local") -> dict:
    """Recommend best days and times to post on a social platform for a local business.

    Args:
        platform: Target platform (`facebook`, `instagram`, `twitter`).
        business_type: Business category (e.g. `restaurant`, `salon`, `retail`, `local`).

    Returns:
        Dictionary of recommended days, time windows, and rationale.
    """
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
    logger.info(
        "[Social Stub] Computed optimal times for platform=%s business_type=%s",
        normalized,
        business_type,
    )
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
