"""Unit tests for the M2M client-credentials token provider (SEC-03)."""

from __future__ import annotations

import httpx
import pytest

from app import auth
from app.config import settings


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    auth._reset_cache_for_tests()
    # default: OIDC configured
    monkeypatch.setattr(settings, "oidc_token_url", "https://auth.test/o/token/")
    monkeypatch.setattr(settings, "oidc_client_id", "dms-classifier")
    monkeypatch.setattr(settings, "oidc_client_secret", "shh")
    monkeypatch.setattr(settings, "oidc_scope", "")
    monkeypatch.setattr(settings, "lookup_bearer", "")
    yield
    auth._reset_cache_for_tests()


async def test_mints_and_sends_bearer(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url == httpx.URL("https://auth.test/o/token/")
        body = dict(httpx.QueryParams(request.content.decode()))
        assert body["grant_type"] == "client_credentials"
        assert body["client_id"] == "dms-classifier"
        return httpx.Response(200, json={"access_token": "TKN", "expires_in": 300})

    _patch_transport(monkeypatch, handler)
    headers = await auth.auth_headers()
    assert headers == {"Authorization": "Bearer TKN"}
    assert calls["n"] == 1


async def test_caches_token(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "CACHED", "expires_in": 300})

    _patch_transport(monkeypatch, handler)
    t1 = await auth.get_token()
    t2 = await auth.get_token()
    assert t1 == t2 == "CACHED"


async def test_refreshes_when_expired(monkeypatch):
    seq = iter(["A", "B"])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": next(seq), "expires_in": 300})

    _patch_transport(monkeypatch, handler)
    assert await auth.get_token() == "A"
    # force expiry
    auth._expires_at = 0.0
    assert await auth.get_token() == "B"


async def test_falls_back_to_static_bearer_when_oidc_unset(monkeypatch):
    monkeypatch.setattr(settings, "oidc_client_id", "")
    monkeypatch.setattr(settings, "lookup_bearer", "STATIC")
    assert await auth.auth_headers() == {"Authorization": "Bearer STATIC"}


async def test_no_header_when_nothing_configured(monkeypatch):
    monkeypatch.setattr(settings, "oidc_client_id", "")
    monkeypatch.setattr(settings, "lookup_bearer", "")
    assert await auth.auth_headers() == {}


async def test_mint_failure_returns_no_header(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    _patch_transport(monkeypatch, handler)
    assert await auth.auth_headers() == {}


def _patch_transport(monkeypatch, handler):
    """Make httpx.AsyncClient use a MockTransport driving `handler`."""
    real_init = httpx.AsyncClient.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
