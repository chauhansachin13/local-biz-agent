"""Lightweight async/sync LLM client supporting Gemini, OpenAI, and Anthropic with fallback."""

from __future__ import annotations

import os
from typing import Any

import httpx

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_keys(overrides: dict[str, Any] | None = None) -> dict[str, str]:
    ctx = overrides or {}
    return {
        "gemini": (
            ctx.get("gemini_api_key")
            or settings.gemini_api_key
            or os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", "")
        ).strip(),
        "openai": (ctx.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")).strip(),
        "anthropic": (ctx.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")).strip(),
    }


async def generate_text_with_llm(
    system_prompt: str,
    user_prompt: str,
    overrides: dict[str, Any] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 450,
) -> str | None:
    """Call Gemini, OpenAI, or Anthropic asynchronously via httpx; return None if unconfigured or on error."""
    keys = _resolve_keys(overrides)

    if keys["gemini"]:
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={keys['gemini']}"
            )
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"parts": [{"text": user_prompt}]}],
                        "generationConfig": {
                            "temperature": temperature,
                            "maxOutputTokens": max_tokens,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates") or []
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini request failed; using fallback: %s", exc)

    if keys["openai"]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {keys['openai']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI request failed; using fallback: %s", exc)

    if keys["anthropic"]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": keys["anthropic"],
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                )
                resp.raise_for_status()
                return resp.json()["content"][0]["text"].strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Anthropic request failed; using fallback: %s", exc)

    return None
