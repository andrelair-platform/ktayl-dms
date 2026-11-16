"""SEC-03: M2M auth for the system-of-record lookups.

The worker authenticates to the claims/policy lookups with an OAuth2 **client-credentials**
access token minted by Authentik (the platform IdP). The target services validate the JWT
against Authentik's JWKS (grant_type=client_credentials; shared issuer) — see
`feedback_crossservice_m2m_auth_wiring` (grant_types / signing-key-kid / consumer netpol /
RFC3339 expiry must align).

The token is cached in-process and refreshed ~30s before the server-stated expiry. When OIDC is
unconfigured (open dev lookup) it falls back to the optional static `lookup_bearer`, then to no
Authorization header — so the image stays env-agnostic (same artifact dev+prod).
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.config import settings

_token: str | None = None
_expires_at: float = 0.0
_lock = asyncio.Lock()


def _oidc_configured() -> bool:
    return bool(settings.oidc_token_url and settings.oidc_client_id and settings.oidc_client_secret)


async def _mint() -> str | None:
    """Mint a fresh access token via the client-credentials grant (caller holds `_lock`)."""
    global _token, _expires_at
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }
    if settings.oidc_scope:
        data["scope"] = settings.oidc_scope
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        resp = await client.post(settings.oidc_token_url, data=data)
    resp.raise_for_status()
    payload = resp.json()
    _token = payload["access_token"]
    # Refresh 30s before the server-stated lifetime (Authentik default 300s if absent).
    _expires_at = time.monotonic() + float(payload.get("expires_in", 300)) - 30.0
    return _token


async def get_token() -> str | None:
    """Return a valid access token (cached), or None when auth isn't available."""
    if not _oidc_configured():
        # OIDC not provisioned yet → the optional static bearer, else unauthenticated (dev).
        return settings.lookup_bearer or None
    if _token and time.monotonic() < _expires_at:
        return _token
    async with _lock:
        # Re-check under the lock: a concurrent caller may have just minted one.
        if _token and time.monotonic() < _expires_at:
            return _token
        try:
            return await _mint()
        except httpx.HTTPError:
            return None


async def auth_headers() -> dict[str, str]:
    """The Authorization header for a lookup call (empty dict when no token is available)."""
    tok = await get_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _reset_cache_for_tests() -> None:
    """Clear the in-process token cache (used by unit tests)."""
    global _token, _expires_at
    _token, _expires_at = None, 0.0
