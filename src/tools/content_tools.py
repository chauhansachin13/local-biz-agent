"""LangChain tools for marketing content ideation, calendars, and promotions.

Provides `@tool` functions and a `ContentTools` wrapper used by the Content
Generation agent.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Dict, List

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_CATEGORY_IDEAS: Dict[str, List[Dict[str, str]]] = {
    "restaurant": [
        {"title": "Chef's Behind-the-Scenes Prep", "format": "Reel / Short Video", "goal": "Authenticity & reach"},
        {"title": "Signature Dish Spotlight", "format": "Carousel Post", "goal": "Foot traffic"},
        {"title": "Customer Favorite Review Quote", "format": "Static Graphic", "goal": "Social proof"},
        {"title": "Weekend Brunch / Dinner Special", "format": "Google Update + Story", "goal": "Bookings"},
        {"title": "Meet the Team Feature", "format": "Portrait Post", "goal": "Community trust"},
    ],
    "salon": [
        {"title": "Before & After Transformation", "format": "Carousel / Reel", "goal": "Bookings"},
        {"title": "3 At-Home Care Tips", "format": "Educational Graphic", "goal": "Saves & shares"},
        {"title": "Stylist Spotlight & Favorite Product", "format": "Story + Post", "goal": "Authority"},
        {"title": "Midweek Open-Slot Flash Offer", "format": "Story + Google Update", "goal": "Fill quiet hours"},
        {"title": "Client Testimonial Highlight", "format": "Quote Graphic", "goal": "Social proof"},
    ],
    "fitness": [
        {"title": "Member Milestone Celebration", "format": "Photo + Caption", "goal": "Retention & referrals"},
        {"title": "60-Second Form Check Tip", "format": "Short Video", "goal": "Engagement"},
        {"title": "Coach Q&A Session", "format": "Stories Poll", "goal": "Community interaction"},
        {"title": "7-Day Intro Pass Offer", "format": "Promo Post", "goal": "Lead generation"},
        {"title": "Class Schedule & Peak Energy Clip", "format": "Reel", "goal": "New sign-ups"},
    ],
}

_DEFAULT_IDEAS: List[Dict[str, str]] = [
    {"title": "Behind-the-Scenes Day in the Life", "format": "Short Video / Reel", "goal": "Brand warmth"},
    {"title": "Customer Story & 5-Star Review Spotlight", "format": "Quote Card", "goal": "Trust & conversions"},
    {"title": "Top 3 FAQs Answered Simply", "format": "Carousel", "goal": "Education & saves"},
    {"title": "Neighborhood / Local Partner Shoutout", "format": "Photo Post", "goal": "Local reach"},
    {"title": "Limited-Time Seasonal Offer", "format": "Promo Graphic + GBP Post", "goal": "Direct bookings"},
    {"title": "Meet the Founder / Team", "format": "Portrait Story", "goal": "Connection"},
    {"title": "Weekend Hours & Booking Reminder", "format": "Text + Image", "goal": "Foot traffic"},
]


@tool
def generate_post_ideas(business_type: str, count: int = 5) -> list:
    """Generate tailored social and local marketing post ideas for a business category.

    Args:
        business_type: Type of local business (e.g. `restaurant`, `salon`, `fitness`, `cafe`, `clinic`).
        count: Number of ideas to return (1 to 15, default 5).

    Returns:
        List of structured post idea dictionaries with `title`, `format`, `goal`, and `hook`.
    """
    count = max(1, min(count, 15))
    normalized = (business_type or "local").strip().lower()

    matched_pool = _DEFAULT_IDEAS
    for key, pool in _CATEGORY_IDEAS.items():
        if key in normalized:
            matched_pool = pool + _DEFAULT_IDEAS
            break

    ideas = []
    for idx in range(count):
        template = matched_pool[idx % len(matched_pool)]
        ideas.append(
            {
                "idea_number": idx + 1,
                "business_type": business_type,
                "title": template["title"],
                "recommended_format": template["format"],
                "primary_goal": template["goal"],
                "suggested_cta": "Book or visit us today — link in bio / Google Profile!",
            }
        )

    logger.info("[Content] Generated %d post ideas for business_type=%s", len(ideas), business_type)
    return ideas


@tool
def create_content_calendar(business_id: str, weeks: int = 4) -> dict:
    """Create a multi-week cross-platform content calendar for a local business.

    Args:
        business_id: Local business identifier.
        weeks: Number of weeks to plan (1 to 12, default 4).

    Returns:
        Dictionary containing weekly schedules across Google Business, Instagram,
        Facebook, and Twitter with themes and posting cadences.
    """
    weeks = max(1, min(weeks, 12))
    start = date.today()
    weekly_templates = [
        ("Monday", "Google Business", "Weekly Update & Hours / Availability Reminder"),
        ("Tuesday", "Instagram", "Behind-the-Scenes Visual or Product/Service Spotlight"),
        ("Thursday", "Facebook", "Customer Testimonial & Community Story"),
        ("Friday", "Twitter", "Quick Tip or Weekend Offer Teaser"),
        ("Saturday", "Instagram", "Weekend Engagement / Promo Call-to-Action"),
    ]

    calendar_weeks = []
    for w in range(weeks):
        week_start = start + timedelta(weeks=w)
        entries = []
        for offset_days, (day_name, platform, theme) in enumerate(weekly_templates):
            post_date = week_start + timedelta(days=offset_days)
            entries.append(
                {
                    "date": post_date.isoformat(),
                    "day": day_name,
                    "platform": platform,
                    "theme": theme,
                    "status": "planned",
                }
            )
        calendar_weeks.append(
            {
                "week": w + 1,
                "week_starting": week_start.isoformat(),
                "posts": entries,
            }
        )

    logger.info(
        "[Content] Built %d-week content calendar for business_id=%s",
        weeks,
        business_id,
    )
    return {
        "business_id": str(business_id),
        "weeks_planned": weeks,
        "cadence": "5 posts/week across Google Business, Instagram, Facebook, and Twitter",
        "calendar": calendar_weeks,
    }


@tool
def generate_promotional_offer(business_name: str, occasion: str) -> str:
    """Draft a promotional offer campaign copy package for a seasonal or local occasion.

    Args:
        business_name: Name of the local business.
        occasion: Occasion or campaign theme (e.g. `Holiday Weekend`, `Grand Reopening`, `Summer Sale`).

    Returns:
        JSON string with offer headline, short SMS/Tweet copy, social post copy, and GBP update copy.
    """
    clean_name = (business_name or "Our Business").strip()
    clean_occasion = (occasion or "Special Event").strip()

    package = {
        "business_name": clean_name,
        "occasion": clean_occasion,
        "headline": f"{clean_occasion} Special at {clean_name}: 15% Off When You Book This Week!",
        "short_copy": (
            f"Celebrate {clean_occasion} with {clean_name}! Enjoy 15% off your next visit — "
            f"limited spots available. Book today!"
        ),
        "social_caption": (
            f"It's {clean_occasion} season at {clean_name}!\n\n"
            f"To thank our amazing local community, we're offering 15% off (or a complimentary "
            f"upgrade) for bookings made before Sunday.\n\n"
            f"Reserve your spot now or stop by and mention '{clean_occasion.upper().replace(' ', '')}'!"
        ),
        "google_business_update": (
            f"{clean_occasion} Offer at {clean_name}: Enjoy 15% off select services all week. "
            f"Tap 'Book' or call us directly to claim your spot."
        ),
        "recommended_promo_code": f"{clean_occasion.split()[0].upper()[:8]}15",
    }

    logger.info(
        "[Content] Generated promotional offer for business=%s occasion=%s",
        clean_name,
        clean_occasion,
    )
    return json.dumps(package, indent=2)


@tool
def generate_blog_outline(
    topic: str, business_name: str, tone: str = "friendly"
) -> dict:
    """Create an SEO-friendly local blog post outline tailored to a business brand tone.

    Args:
        topic: Subject of the blog post.
        business_name: Name of the local business.
        tone: Desired brand voice (`friendly`, `professional`, `luxury`, `playful`).

    Returns:
        Dictionary with SEO title options, meta description, section headings, and CTA.
    """
    logger.info(
        "[Content] Created blog outline topic=%s business=%s tone=%s",
        topic,
        business_name,
        tone,
    )
    return {
        "business_name": business_name,
        "topic": topic,
        "tone": tone,
        "seo_titles": [
            f"{topic}: A Local Guide from {business_name}",
            f"Everything You Need to Know About {topic} | {business_name}",
        ],
        "meta_description": (
            f"Discover practical tips on {topic} from {business_name}. "
            f"Trusted local expertise with easy online booking."
        ),
        "sections": [
            {"heading": f"Why {topic} Matters for Our Local Community", "key_points": ["Customer pain point", "Local context"]},
            {"heading": "3 Practical Tips You Can Use Right Away", "key_points": ["Actionable tip 1", "Actionable tip 2", "Common mistake to avoid"]},
            {"heading": f"How {business_name} Helps", "key_points": ["Signature service", "Customer testimonial", "Easy next step"]},
        ],
        "call_to_action": f"Ready to experience the difference? Book your visit with {business_name} today.",
    }


class ContentTools:
    """Collection wrapper for Content Generation LangChain tools."""

    generate_post_ideas = generate_post_ideas
    create_content_calendar = create_content_calendar
    generate_promotional_offer = generate_promotional_offer
    generate_blog_outline = generate_blog_outline

    @classmethod
    def get_tools(cls) -> list:
        """Return all Content Generation tools as a list."""
        return [
            generate_post_ideas,
            create_content_calendar,
            generate_promotional_offer,
            generate_blog_outline,
        ]
