"""Bridge invoking live LangGraph ReAct specialist agents when an LLM API key is active."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from config.settings import settings
from src.agents.analytics_agent import create_analytics_agent
from src.agents.content_generator import create_content_agent
from src.agents.google_business import create_google_business_agent
from src.agents.review_manager import create_review_agent
from src.agents.social_media import create_social_media_agent
from src.utils.logger import get_logger

logger = get_logger(__name__)

_FACTORIES = {
    "google_profile": ("GoogleBusinessReActAgent", create_google_business_agent),
    "social_create": ("SocialMediaReActAgent", create_social_media_agent),
    "review_respond": ("ReviewManagerReActAgent", create_review_agent),
    "content_plan": ("ContentGeneratorReActAgent", create_content_agent),
    "analytics_overview": ("AnalyticsReActAgent", create_analytics_agent),
}


def has_gemini_key(overrides: dict[str, Any] | None = None) -> str:
    """Return active Gemini API key if present in overrides, settings, or env."""
    ctx = overrides or {}
    return str(
        ctx.get("gemini_api_key")
        or settings.gemini_api_key
        or os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
    ).strip()


async def run_react_specialist(
    domain: str,
    business_context: str,
    user_request: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Invoke the matching LangGraph ReAct specialist agent and extract tool traces.

    Returns None when no Gemini key is configured or on transient API error so the
    supervisor seamlessly falls back to deterministic SQLite execution.
    """
    key = has_gemini_key(overrides)
    if not key or domain not in _FACTORIES:
        return None

    agent_label, factory = _FACTORIES[domain]
    prev_env = os.environ.get("GEMINI_API_KEY")
    try:
        os.environ["GEMINI_API_KEY"] = key
        compiled = factory()
        prompt = f"Business Context:\n{business_context}\n\nTask:\n{user_request}"
        result = await compiled.ainvoke({"messages": [HumanMessage(content=prompt)]})
        msgs = result.get("messages") or []

        tool_traces: list[dict[str, Any]] = []
        final_text = ""
        for msg in msgs:
            if isinstance(msg, ToolMessage):
                tool_traces.append(
                    {
                        "agent": agent_label,
                        "tool": msg.name or "tool_call",
                        "status": "completed",
                        "detail": str(msg.content)[:160],
                    }
                )
            elif (
                isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip()
            ):
                final_text = msg.content.strip()

        if not final_text:
            return None
        return {
            "agent": agent_label,
            "reply": final_text,
            "tool_traces": tool_traces,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ReAct specialist '%s' failed; using deterministic fallback: %s", domain, exc
        )
        return None
    finally:
        if prev_env is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = prev_env
