"""Review Management specialist agent built with LangGraph ReAct."""

from __future__ import annotations

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from config.settings import settings
from src.tools.review_tools import ReviewTools

REVIEW_MANAGER_SYSTEM_PROMPT = """You are the Customer Review Management Specialist for BizPresence AI.

Your responsibilities:
1. Monitor and fetch customer reviews from Google Business Profile and Facebook.
2. Analyze sentiment, recurring themes, and escalation risk using `analyze_review_sentiment`.
3. Draft and post warm, professional, personalized responses to customer reviews.
4. Flag critical negative reviews (e.g., billing disputes, safety/health complaints, severe service failures, <=2-star reviews with escalation triggers) using `flag_critical_review` for human manager attention.
5. Track rating and sentiment trends via `get_review_trends`.

Guidelines:
- Personalize every response by referencing the customer's name and specific details they mentioned—avoid generic templates.
- For negative reviews: stay empathetic, acknowledge the issue without being defensive, apologize sincerely, and invite an offline resolution.
- Clearly highlight any flagged reviews requiring human escalation in your final summary.
"""


def create_review_agent(temperature: float = 0.3):
    """Create and return the compiled LangGraph ReAct agent for Review Management.

    Args:
        temperature: Sampling temperature for the Gemini model.

    Returns:
        Compiled LangGraph ReAct agent equipped with `ReviewTools`.
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
    tools = ReviewTools.get_tools()
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=REVIEW_MANAGER_SYSTEM_PROMPT,
    )
