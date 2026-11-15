"""Langfuse LLMOps (llmops.md): a dedicated project trace tree + label-routed prompt management with a
Git-seeded fallback. Dev + prod share one project via the `environment` attribute."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from app.config import settings

_lf: Any = None
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def langfuse() -> Any:
    """The Langfuse client (None if keys aren't configured — tracing is best-effort, never blocks a file)."""
    global _lf
    if _lf is None and settings.langfuse_public_key and settings.langfuse_secret_key:
        from langfuse import Langfuse

        _lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _lf


def new_trace(name: str, document_id: str, inp: Any = None) -> Any:
    lf = langfuse()
    if not lf:
        return None
    return lf.trace(
        name=name,
        input=inp,
        user_id="dms-classifier",
        session_id=document_id,
        metadata={"environment": settings.environment, "document_id": document_id},
        tags=[settings.environment],
    )


def get_prompt(name: str, fallback_file: str) -> str:
    """Managed prompt from Langfuse (label-routed), falling back to the Git-committed seed."""
    lf = langfuse()
    if lf:
        try:
            return lf.get_prompt(name, label=settings.langfuse_prompt_label).prompt
        except Exception:
            pass
    return (_PROMPT_DIR / fallback_file).read_text(encoding="utf-8")


def flush() -> None:
    lf = langfuse()
    if lf:
        with contextlib.suppress(Exception):
            lf.flush()
