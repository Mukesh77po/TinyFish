"""Every embedding call goes through here (PLAN.md §4.1). Returns None instead of raising, so ranking
can fall back to keyword overlap when the key is missing or the network is down."""
import logging
import os

import openai

from api.config import EMBEDDING_DIM, fallback_mode  # also loads .env

log = logging.getLogger("api.embeddings")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
_client: openai.AsyncOpenAI | None = None


def enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and not fallback_mode()


def _oa() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(timeout=20.0, max_retries=2)
    return _client


async def embed(texts: list[str]) -> list[list[float]] | None:
    if not texts or not enabled():
        return None
    try:
        resp = await _oa().embeddings.create(model=EMBEDDING_MODEL, input=texts, dimensions=EMBEDDING_DIM)
    except openai.OpenAIError as e:
        log.warning("embedding failed (%d texts): %s", len(texts), e)
        return None
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


def tender_text(title: str, item: str | None, buyer: str | None) -> str:
    return " | ".join(x for x in (title, item, buyer) if x)


def profile_text(products: list[str], keywords: list[str], hsn_codes: list[str]) -> str:
    parts = [", ".join(products), ", ".join(keywords)]
    if hsn_codes:
        parts.append("HSN " + ", ".join(hsn_codes))
    return " | ".join(p for p in parts if p)
