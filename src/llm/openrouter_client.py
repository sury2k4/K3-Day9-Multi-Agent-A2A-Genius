"""Bounded OpenRouter calls with transient retry and one JSON repair."""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Generic, TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from src.config.model_config import LLM_TEMPERATURE, OPENROUTER_MODEL_ID
from src.config.settings import Settings
from src.errors import LLMRequestError, LLMStructuredOutputError

T = TypeVar("T", bound=BaseModel)
FENCE_PATTERN = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class StructuredResponse(Generic[T]):
    value: T
    prompt_tokens: int = 0
    completion_tokens: int = 0


def parse_json_payload(content: str) -> object:
    match = FENCE_PATTERN.match(content)
    candidate = match.group(1) if match else content.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMStructuredOutputError(f"Model returned invalid JSON: {exc.msg}") from exc


def is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


class OpenRouterClient:
    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        settings.require_api_key()
        self._settings = settings
        self._client = client or AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=settings.llm_request_timeout_seconds,
            default_headers={
                "HTTP-Referer": "https://localhost/olist-multi-agent-lab",
                "X-Title": "K3 Day 09 Multi-Agent Dispute Resolution",
            },
        )
        self._semaphore = semaphore or asyncio.Semaphore(settings.max_concurrent_llm_calls)

    async def structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        response_model: type[T],
    ) -> StructuredResponse[T]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
        ]
        first = await self._request(messages)
        try:
            value = response_model.model_validate(parse_json_payload(first[0]))
            return StructuredResponse(value, first[1], first[2])
        except (LLMStructuredOutputError, ValidationError) as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": first[0]},
                {
                    "role": "user",
                    "content": (
                        "Return corrected JSON only. It must match this JSON Schema exactly: "
                        + json.dumps(response_model.model_json_schema(), ensure_ascii=False)
                    ),
                },
            ]
            second = await self._request(repair_messages)
            try:
                value = response_model.model_validate(parse_json_payload(second[0]))
            except (LLMStructuredOutputError, ValidationError) as exc:
                raise LLMStructuredOutputError(
                    f"Structured output repair failed: {exc}"
                ) from first_error
            return StructuredResponse(
                value,
                first[1] + second[1],
                first[2] + second[2],
            )

    async def _request(self, messages: list[dict[str, str]]) -> tuple[str, int, int]:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max(1, self._settings.llm_max_retries + 1)),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                retry=retry_if_exception(is_transient_error),
                reraise=True,
            ):
                with attempt:
                    async with self._semaphore:
                        response = await self._client.chat.completions.create(
                            model=OPENROUTER_MODEL_ID,
                            messages=messages,  # type: ignore[arg-type]
                            temperature=LLM_TEMPERATURE,
                            response_format={"type": "json_object"},
                        )
                    content = response.choices[0].message.content
                    if not content:
                        raise LLMStructuredOutputError("Model returned empty content")
                    usage = response.usage
                    return (
                        content,
                        int(usage.prompt_tokens) if usage else 0,
                        int(usage.completion_tokens) if usage else 0,
                    )
        except LLMStructuredOutputError:
            raise
        except Exception as exc:
            raise LLMRequestError(f"OpenRouter request failed: {type(exc).__name__}") from exc
        raise LLMRequestError("OpenRouter request ended without a response")
