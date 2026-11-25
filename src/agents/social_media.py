"""Social Media specialist agent built with LangGraph ReAct."""

from __future__ import annotations

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import settings
from src.tools.social_tools import SocialMediaTools

SOCIAL_MEDIA_SYSTEM_PROMPT = """You are the Social Media Specialist for BizPresence AI.

Your responsibilities:
1. Craft platform-tailored posts for Facebook, Instagram, and Twitter/X.
   - Facebook: conversational, community-oriented, informative.
   - Instagram: visual-first storytelling captions with relevant local + niche hashtags (requires an image_url when publishing).
   - Twitter/X: punchy, under 280 characters.
2. Recommend optimal posting windows using `get_optimal_posting_times` and schedule posts with `schedule_post`.
3. Cross-post campaigns across platforms while adapting copy and formatting for each channel.
4. Retrieve and interpret engagement metrics via `get_social_metrics`.

Guidelines:
- Never exceed 280 characters for Twitter/X posts.
- If the user wants to publish immediately to Instagram without providing an `image_url`, either schedule it, generate draft copy + hashtags, or ask for the image URL before calling `post_to_instagram`.
- Report all published or scheduled post IDs, platforms, hashtags, and timestamps clearly.
"""


def create_social_media_agent(temperature: float = 0.6):
    """Create and return the compiled LangGraph ReAct agent for Social Media management.

    Args:
        temperature: Sampling temperature for the Gemini model.

    Returns:
        Compiled LangGraph ReAct agent equipped with `SocialMediaTools`.
    """
    api_key = (
        getattr(settings, "gemini_api_key", None)
        or getattr(settings, "GOOGLE_API_KEY", None)
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
    )
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=api_key,
        temperature=temperature,
    )
    tools = SocialMediaTools.get_tools()
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SOCIAL_MEDIA_SYSTEM_PROMPT,
    )
