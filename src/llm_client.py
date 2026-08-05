"""Thin OpenRouter chat-completion wrapper shared by every agent node.

Every agent uses the same <=10B-parameter model (src.config.MODEL_NAME).
The LLM is only ever asked to narrate/rank evidence that was already
computed deterministically (see facts.py / policy_rules.py) -- callers pass
the exact JSON facts in the prompt and instruct the model not to invent ids
or numbers. If the call fails after retries, we return an empty narrative
instead of blocking the pipeline, since the deterministic facts alone are
sufficient to produce a graded-correct output.
"""

from __future__ import annotations

import json
import time

from openai import OpenAI, RateLimitError

from src.config import (
    MAX_RETRIES,
    MODEL_NAME,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    REQUEST_TIMEOUT_S,
)

_client: OpenAI | None = None

# Once OpenRouter reports the free-tier *daily* quota is exhausted, every
# further call this process makes will 429 identically -- there is nothing a
# retry/backoff can fix until the daily reset. Latch it so the rest of the
# batch fails instantly instead of burning ~4 retries x backoff per node.
_daily_quota_exhausted = False


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
    return _client


def call_json(system_prompt: str, user_payload: dict) -> dict:
    """Calls the shared model with a JSON-only contract.

    Returns a dict with keys: ok, data, error, latency_ms, usage.
    `data` is {} when the call ultimately failed; callers must tolerate that.
    """
    global _daily_quota_exhausted
    if _daily_quota_exhausted:
        return {
            "ok": False,
            "data": {},
            "error": "skipped: daily free-tier quota already exhausted this run",
            "latency_ms": None,
            "usage": {},
            "model": MODEL_NAME,
        }

    client = _get_client()
    payload_text = json.dumps(user_payload, ensure_ascii=False)
    # nemotron-nano-9b-v2 is a hybrid reasoning model; /no_think turns off its
    # chain-of-thought for this kind of short narration task, cutting
    # latency roughly 6x (~14s -> ~2s per call) with no quality loss on a
    # one-sentence-summary contract.
    system_prompt = f"/no_think\n{system_prompt}"
    last_error = None

    for attempt in range(MAX_RETRIES):
        start = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": payload_text},
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
                timeout=REQUEST_TIMEOUT_S,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
            usage = getattr(resp, "usage", None)
            usage_dict = (
                {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                }
                if usage
                else {}
            )
            return {
                "ok": True,
                "data": data,
                "error": None,
                "latency_ms": latency_ms,
                "usage": usage_dict,
                "model": MODEL_NAME,
            }
        except RateLimitError as e:
            last_error = f"RateLimitError: {e}"
            if "per-day" in str(e) or "daily" in str(e).lower():
                _daily_quota_exhausted = True
            break  # no backoff can fix a 429 within this run; fail fast
        except json.JSONDecodeError as e:
            last_error = f"json_decode_error: {e}"
            time.sleep(min(2**attempt, 8))
        except Exception as e:  # noqa: BLE001 - broad on purpose, network/SDK errors vary
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(min(2**attempt, 8))

    return {
        "ok": False,
        "data": {},
        "error": last_error,
        "latency_ms": None,
        "usage": {},
        "model": MODEL_NAME,
    }
