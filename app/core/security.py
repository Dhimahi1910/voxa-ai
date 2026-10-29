"""Authentication dependencies. Fail closed: with no keys configured every protected route returns 503."""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Query, status

from app.core.config import Settings, get_settings


def _match(candidate: str, keys: list[str]) -> bool:
    ok = False
    for k in keys:  # compare against every key to avoid early-exit timing differences
        ok |= hmac.compare_digest(candidate.encode(), k.encode())
    return ok


def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    keys = settings.admin_keys
    if not keys:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEYS is not configured")
    if not x_api_key or not _match(x_api_key, keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


def require_webhook_secret(
    x_webhook_secret: str | None = Header(default=None),
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    secret = settings.webhook_secret.get_secret_value()
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WEBHOOK_SECRET is not configured")
    supplied = x_webhook_secret or token or ""
    if not _match(supplied, [secret]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")
