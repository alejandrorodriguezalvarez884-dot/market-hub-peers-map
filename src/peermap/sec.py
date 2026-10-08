"""SEC EDGAR: free and official. Only the batch that builds the map calls it, never the service."""

from __future__ import annotations

import os

import httpx

from .config import SEC_RPS
from .http import RateLimiter, get_json, get_text

_limiter = RateLimiter(SEC_RPS)


def _headers() -> dict[str, str]:
    agent = os.environ.get("SEC_USER_AGENT", "").strip() or "market-hub-peers-map contact@example.com"
    return {"User-Agent": agent, "Accept-Encoding": "gzip, deflate"}


def sec_get(url: str, client: httpx.Client | None = None):
    return get_json(url, source="SEC", headers=_headers(), limiter=_limiter, client=client)


def sec_get_text(url: str, client: httpx.Client | None = None) -> str:
    """A filing's document. They run to tens of megabytes, so the timeout is longer."""
    return get_text(url, source="SEC", headers=_headers(), limiter=_limiter, client=client, timeout=120)
