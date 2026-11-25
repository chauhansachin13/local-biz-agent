"""Digital Presence Analytics specialist agent built with LangGraph ReAct."""

from __future__ import annotations

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import settings
from src.tools.analytics_tools import AnalyticsTools

ANALYTICS_AGENT_SYSTEM_PROMPT = """You are the Digital Presence Analytics Specialist for BizPresence AI.

Your responsibilities:
1. Aggregate cross-platform metrics (Google Business Profile, Social Media, Reviews, and Bookings) via `aggregate_platform_metrics`.
2. Generate executive weekly and monthly performance reports with `generate_performance_report`.
3. Identify meaningful trends in customer engagement, ratings, and appointment demand using `identify_trends`.
4. Recommend prioritized, data-backed improvements via `suggest_data_improvements`.

Guidelines:
- Lead with an executive takeaway, then present concrete numbers and percentage changes cleanly.
- Ground every recommendation in observed metrics and explain the expected business impact.
- Distinguish clearly between high-priority quick wins and longer-term optimizations.
"""


def create_analytics_agent(temperature: float = 0.2):
    """Create and return the compiled LangGraph ReAct agent for Analytics & Reporting.

    Args:
        temperature: Sampling temperature for the Gemini model.

    Returns:
        Compiled LangGraph ReAct agent equipped with `AnalyticsTools`.
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
    tools = AnalyticsTools.get_tools()
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=ANALYTICS_AGENT_SYSTEM_PROMPT,
    )
