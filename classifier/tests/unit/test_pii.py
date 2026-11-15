"""L1 — SEC-01: the masker redacts via Presidio and FAILS CLOSED if Presidio is down."""

import httpx
import pytest
import respx

from app import pii


@respx.mock
async def test_mask_redacts_pii_keeps_identifiers() -> None:
    respx.post(f"{pii.settings.presidio_analyzer_url}/analyze").mock(
        return_value=httpx.Response(200, json=[{"entity_type": "PERSON", "start": 0, "end": 4, "score": 0.9}])
    )
    respx.post(f"{pii.settings.presidio_anonymizer_url}/anonymize").mock(
        return_value=httpx.Response(200, json={"text": "<REDACTED> policy POL-7"})
    )
    out = await pii.mask("John policy POL-7")
    assert "<REDACTED>" in out and "POL-7" in out


@respx.mock
async def test_mask_no_entities_returns_text() -> None:
    respx.post(f"{pii.settings.presidio_analyzer_url}/analyze").mock(return_value=httpx.Response(200, json=[]))
    out = await pii.mask("policy POL-7")
    assert out == "policy POL-7"


@respx.mock
async def test_mask_fails_closed_when_presidio_down() -> None:
    respx.post(f"{pii.settings.presidio_analyzer_url}/analyze").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await pii.mask("secret name")
