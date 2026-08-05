from __future__ import annotations

from typing import Any

from .config import Settings


def build_llm(settings: Settings) -> Any | None:
    """Create the OpenRouter-backed Qwen client, or None for deterministic offline runs."""

    if not settings.openrouter_configured:
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        temperature=0,
        max_tokens=8192,
        timeout=180,
        max_retries=0,
        # Qwen3.5 consumes nearly the entire completion budget on hidden
        # reasoning even at low/minimal effort, leaving no structured summary.
        # Keep a large output ceiling but disable reasoning for this concise,
        # non-authoritative explanation. The deterministic Policy Engine
        # remains authoritative for scoring.
        extra_body={"reasoning": {"effort": "none"}},
    )
