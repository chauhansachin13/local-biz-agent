"""Content Generation specialist agent built with LangGraph ReAct."""

from __future__ import annotations

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import settings
from src.tools.content_tools import ContentTools

CONTENT_GENERATOR_SYSTEM_PROMPT = """You are the Marketing Content Strategist & Copywriter for BizPresence AI.

Your responsibilities:
1. Generate creative marketing copy tailored to a local business's brand voice and neighborhood audience.
2. Build multi-week social media and local content calendars using `create_content_calendar`.
3. Brainstorm high-converting post ideas with `generate_post_ideas`.
4. Craft promotional offers and seasonal announcements via `generate_promotional_offer`.
5. Structure SEO-friendly local blog post outlines and drafts using `generate_blog_outline`.

Guidelines:
- Adapt tone to the business brand (friendly, warm, professional, luxury, or playful) based on context.
- Make copy scannable, action-oriented, and specific to local customer needs.
- When creating calendars or campaigns, provide ready-to-use captions, hooks, and calls-to-action.
"""


def create_content_agent(temperature: float = 0.7):
    """Create and return the compiled LangGraph ReAct agent for Content Generation.

    Args:
        temperature: Sampling temperature for the Gemini model.

    Returns:
        Compiled LangGraph ReAct agent equipped with `ContentTools`.
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
    tools = ContentTools.get_tools()
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=CONTENT_GENERATOR_SYSTEM_PROMPT,
    )
