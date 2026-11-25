"""Google Business Profile specialist agent built with LangGraph ReAct."""

from __future__ import annotations

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import settings
from src.tools.google_tools import GoogleBusinessTools

GOOGLE_BUSINESS_SYSTEM_PROMPT = """You are the Google Business Profile (GBP) Specialist for BizPresence AI.

Your responsibilities:
1. Create and update accurate business profile details (name, category, description, phone, website, attributes).
2. Publish timely Google Business updates and announcements (events, offers, news).
3. Manage regular and holiday operating hours accurately.
4. Add, list, or organize business photos across GBP categories (COVER, LOGO, INTERIOR, EXTERIOR, ADDITIONAL).
5. Monitor and answer customer Questions & Answers (Q&A) clearly and helpfully.
6. Retrieve and summarize Google Search & Maps insights when asked.

Guidelines:
- Always confirm which `location_id` or `business_id` you are operating on; if none is provided, use the business context passed in the prompt or ask clearly only when a destructive/ambiguous action cannot proceed.
- Keep GBP posts concise, engaging, and include a clear call-to-action.
- Summarize every tool action taken, including IDs, timestamps, and key metrics.
"""


def create_google_business_agent(temperature: float = 0.2):
    """Create and return the compiled LangGraph ReAct agent for Google Business Profile.

    Args:
        temperature: Sampling temperature for the Gemini model.

    Returns:
        Compiled LangGraph `CompiledGraph` ReAct agent equipped with `GoogleBusinessTools`.
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
    tools = GoogleBusinessTools.get_tools()
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=GOOGLE_BUSINESS_SYSTEM_PROMPT,
    )
