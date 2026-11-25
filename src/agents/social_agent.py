"""Social media content generation agent."""

from __future__ import annotations

import re
from typing import Any

from src.agents.llm_client import generate_text_with_llm
from src.models.business import Business

BEST_POST_TIMES: dict[str, str] = {
    "instagram": "11:30 AM or 6:30 PM local time",
    "facebook": "1:00 PM or 4:00 PM local time",
    "google": "10:00 AM local time",
    "twitter": "12:15 PM or 5:30 PM local time",
}


class SocialMediaAgent:
    """Generates platform-specific social media copy, hashtags, and visual prompts."""

    async def generate_post(
        self,
        business: Business,
        platform: str = "instagram",
        topic: str = "",
        tone: str = "friendly and engaging",
        include_hashtags: bool = True,
        call_to_action: str = "",
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate tailored post copy, hashtags, best time, and image prompt."""
        platform_clean = (platform or "instagram").lower().strip()
        resolved_topic = topic.strip() or f"Featured offering at {business.name}"
        cta = call_to_action.strip() or (
            f"Visit or book with us today at {business.website or business.phone or business.name}!"
        )

        system_prompt = (
            "You are an expert local business social media strategist. "
            "Write concise, high-converting posts tailored to the platform and local community. "
            "Return ONLY the post body copy without hashtags."
        )
        user_prompt = (
            f"Business: {business.name} ({business.category})\n"
            f"Location: {business.city or ''}, {business.state or ''}\n"
            f"Description: {business.description or ''}\n"
            f"Platform: {platform_clean}\n"
            f"Topic: {resolved_topic}\n"
            f"Tone: {tone}\n"
            f"Call to action: {cta}\n"
            "Write an engaging 2-4 sentence social post."
        )

        llm_copy = await generate_text_with_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            overrides=overrides,
            temperature=0.75,
            max_tokens=300,
        )

        content = llm_copy or self._fallback_copy(
            business=business,
            platform=platform_clean,
            topic=resolved_topic,
            tone=tone,
            cta=cta,
        )
        hashtags = (
            self._build_hashtags(business, platform_clean, resolved_topic)
            if include_hashtags
            else []
        )

        return {
            "platform": platform_clean,
            "content": content,
            "hashtags": hashtags,
            "best_time_to_post": BEST_POST_TIMES.get(platform_clean, "11:00 AM local time"),
            "image_prompt": (
                f"Warm editorial lifestyle photograph for {business.name} ({business.category}) "
                f"highlighting {resolved_topic}, natural lighting, inviting neighborhood atmosphere."
            ),
        }

    def _fallback_copy(
        self,
        business: Business,
        platform: str,
        topic: str,
        tone: str,
        cta: str,
    ) -> str:
        city_part = f" in {business.city}" if business.city else ""
        category = (business.category or "").lower()

        if any(k in category for k in ("restaurant", "cafe", "bakery", "food")):
            hook = f"Craving something unforgettable{city_part}?"
            body = (
                f"At {business.name}, we're spotlighting {topic}—crafted fresh daily "
                "with quality ingredients and warm hospitality."
            )
        elif any(k in category for k in ("salon", "spa", "beauty")):
            hook = f"Treat yourself to a fresh glow{city_part}!"
            body = (
                f"Our team at {business.name} specializes in {topic} so you leave "
                "feeling confident, relaxed, and refreshed."
            )
        else:
            hook = f"Local spotlight at {business.name}{city_part}!"
            body = f"Discover {topic} with our dedicated team—trusted service tailored to our community."

        if platform == "twitter":
            return f"{hook} {body} {cta}"[:265]
        if "professional" in tone.lower():
            return f"{body} {cta}"
        return f"{hook} {body} {cta}"

    def _build_hashtags(self, business: Business, platform: str, topic: str) -> list[str]:
        if platform == "google":
            return []
        slug = lambda s: "#" + re.sub(r"[^a-zA-Z0-9]", "", s)  # noqa: E731
        tags = [slug(business.name)]
        if business.city:
            tags.append(slug(f"{business.city}{business.category}"))
            tags.append(slug(f"SupportLocal{business.city}"))
        if business.category:
            tags.append(slug(business.category))
        for word in re.findall(r"[a-zA-Z]{4,}", topic)[:2]:
            tags.append(slug(word))
        tags.extend(["#LocalBusiness", "#ShopLocal"])

        seen: set[str] = set()
        unique: list[str] = []
        for tag in tags:
            low = tag.lower()
            if len(tag) > 2 and low not in seen:
                seen.add(low)
                unique.append(tag)
        return unique[:7]
