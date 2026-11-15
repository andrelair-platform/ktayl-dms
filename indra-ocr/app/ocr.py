"""indra OCR adapter — the single place that touches the ``indra_ocr`` library.

ADR-002 (ktayl-dms): indra is the DMS scan/image OCR engine (CPU-only, self-hosted). This module
wraps the library's ``load() → convert()`` API and normalises each page into a plain dict so the rest
of the service (and its consumers — the Phase-2 classifier) never depends on indra's object shapes.
If indra's API ever changes, this file is the only thing to update (see ADR-002 reversibility note).

The model is loaded once per process (lazy singleton) and is **baked into the image at build time**
(``INDRA_OCR_MODEL_DIR``) because the runtime cluster is default-deny-egress — there is no HuggingFace
fetch at runtime.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import indra_ocr  # type: ignore[import-untyped]

_model: Any = None
_lock = threading.Lock()


def _get_model() -> Any:
    """Load the indra model once per process (thread-safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                threads = int(os.getenv("INDRA_OCR_THREADS", "4"))
                _model = indra_ocr.load(threads=threads)
    return _model


def warm() -> None:
    """Force the model to load (used by the startup lifespan + the image-bake step)."""
    _get_model()


def _box(line: Any) -> list[float] | None:
    box = getattr(line, "box", None)
    if box is None:
        box = getattr(line, "bbox", None)
    if box is None:
        return None
    try:
        return [float(v) for v in box]
    except TypeError:
        return None


def _line_to_dict(line: Any) -> dict[str, Any]:
    return {
        "text": getattr(line, "text", "") or "",
        "bbox": _box(line),
        "confidence": getattr(line, "conf", None),
    }


def run_ocr(path: str) -> dict[str, Any]:
    """OCR a PDF/image file at ``path`` → a normalised result dict.

    Returns::

        {
          "text":  "<all page text joined>",
          "pages": [ {"page": 0, "markdown": "...", "text": "...",
                      "lines": [{"text": ..., "bbox": [...], "confidence": ...}]} ]
        }
    """
    model = _get_model()
    pages: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for index, page in model.convert(path):
        raw_lines = getattr(page, "lines", []) or []
        lines = [_line_to_dict(line) for line in raw_lines]
        page_text = getattr(page, "text", None) or "\n".join(line["text"] for line in lines)
        pages.append(
            {
                "page": index,
                "markdown": getattr(page, "markdown", None),
                "text": page_text,
                "lines": lines,
            }
        )
        text_parts.append(page_text)

    return {"text": "\n\n".join(text_parts), "pages": pages}
