"""Every LLM call goes through here (PLAN.md §4.1). Model names come from env only.

Provider: Groq's free tier (OpenAI-compatible API). gpt-oss supports strict JSON-schema output,
so answers always match the Pydantic schema we pass.
"""
import json
import logging
import os
from typing import TypeVar

import openai
from pydantic import BaseModel, ValidationError

import api.config  # noqa: F401  (loads .env before the env reads below, in every entry point)

log = logging.getLogger("api.llm")

LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", "openai/gpt-oss-20b")
# Reasoning effort (low | medium | high). Extraction from one document is routine work; raise if parse quality drops.
LLM_EFFORT = os.getenv("LLM_EFFORT", "medium")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
# Free tier allows 8k tokens/minute, prompt + answer. A GeM bid's eligibility table is on its first pages.
LLM_MAX_DOC_CHARS = int(os.getenv("LLM_MAX_DOC_CHARS", "14000"))
# Parallel extractions a sweep may run: the free tier only fits about one document a minute.
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "1"))
# SDK retries on 429/5xx/connection errors with backoff (honouring retry-after) before we give up.
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))

T = TypeVar("T", bound=BaseModel)
_client: openai.AsyncOpenAI | None = None


class LLMError(Exception):
    """The model could not produce a valid answer. Callers degrade (e.g. verdict CHECK_DOCS)."""


def _llm() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        # A 429 here usually means "wait for the next minute"; the SDK honours retry-after.
        _client = openai.AsyncOpenAI(api_key=os.getenv("GROQ_API_KEY") or "missing", base_url=GROQ_BASE_URL,
                                     timeout=120.0, max_retries=LLM_MAX_RETRIES)
    return _client


def _strict_schema(schema: type[BaseModel]) -> dict:
    """Pydantic JSON schema in the form strict mode accepts: every object closed and fully required."""
    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                close(v)
        elif isinstance(node, list):
            for v in node:
                close(v)
        return node
    return close(schema.model_json_schema())


async def extract(system: str, text: str, schema: type[T], *, fast: bool = False) -> T:
    """Structured extraction: returns a validated `schema` instance or raises LLMError.

    One retry on an unusable answer (CLAUDE.md: validate, retry once, then give up).
    """
    fmt = {"type": "json_schema",
           "json_schema": {"name": schema.__name__, "strict": True, "schema": _strict_schema(schema)}}
    last = "no answer"
    for attempt in (1, 2):
        try:
            resp = await _llm().chat.completions.create(
                model=LLM_MODEL_FAST if fast else LLM_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
                response_format=fmt,
                reasoning_effort=LLM_EFFORT if LLM_EFFORT in ("low", "medium", "high") else "medium",
                max_completion_tokens=3000,
            )
        except openai.AuthenticationError as e:
            raise LLMError("GROQ_API_KEY missing or invalid") from e
        except openai.RateLimitError as e:
            raise LLMError("Groq rate limit (free tier: 8k tokens/min); try again in a minute") from e
        except openai.APIStatusError as e:
            raise LLMError(f"Groq API error {e.status_code}: {e.message}") from e
        except openai.APIConnectionError as e:
            raise LLMError("cannot reach the Groq API") from e

        msg = resp.choices[0].message
        if getattr(msg, "refusal", None):
            raise LLMError(f"model declined: {msg.refusal}")
        try:
            return schema.model_validate(json.loads(msg.content or ""))
        except (ValueError, ValidationError) as e:
            last = f"invalid answer ({type(e).__name__}, finish_reason={resp.choices[0].finish_reason})"
            log.warning("%s (attempt %d)", last, attempt)
    raise LLMError(last)
