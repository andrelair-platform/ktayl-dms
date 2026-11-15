"""The LLM extraction step: masked OCR text → a business-key candidate, via LiteLLM, Langfuse-traced."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.tracing import get_prompt

_client = AsyncOpenAI(
    base_url=f"{settings.litellm_base_url}/v1",
    api_key=settings.litellm_api_key or "sk-none",
)


class Candidate(BaseModel):
    kind: Literal["policy", "claim", "unknown"] = "unknown"
    number: str | None = None
    client: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _parse(content: str) -> Candidate:
    """Parse the model's JSON (tolerant of a stray prose wrapper)."""
    try:
        return Candidate.model_validate_json(content)
    except Exception:
        pass
    m = re.search(r"\{.*\}", content, re.S)
    if m:
        try:
            return Candidate.model_validate(json.loads(m.group(0)))
        except Exception:
            pass
    return Candidate()  # unknown / confidence 0 → routes to HITL


async def extract(masked_text: str, trace: Any = None) -> Candidate:
    prompt = get_prompt("dms-extract", "extract.txt")
    gen = trace.generation(name="extract", model=settings.classifier_model, input=masked_text) if trace else None
    resp = await _client.chat.completions.create(
        model=settings.classifier_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": masked_text[:8000]},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content or ""
    cand = _parse(content)
    if gen is not None:
        usage = getattr(resp, "usage", None)
        gen.end(
            output=content,
            usage={
                "promptTokens": getattr(usage, "prompt_tokens", None),
                "completionTokens": getattr(usage, "completion_tokens", None),
            }
            if usage
            else None,
        )
    return cand
