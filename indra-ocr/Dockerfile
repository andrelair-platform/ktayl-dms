# indra OCR service — CPU-only, self-hosted (ADR-002). The ~76 MB model is BAKED into the image's
# HuggingFace cache (HF_HOME) at build time, then the runtime runs HF_HUB_OFFLINE=1 — because the
# runtime cluster is default-deny-egress (no HuggingFace fetch at run time).
#
# Note: indra only auto-downloads when INDRA_OCR_MODEL_DIR is UNSET (it then snapshot_download's
# datalab-to/indra-ocr into the HF cache). Pointing it at a custom empty dir makes load() expect the
# files already present — so we bake the HF cache, not a custom model dir.
FROM python:3.12-slim

ENV HF_HOME=/opt/indra/hf \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# opencv-python-headless needs libglib; onnxruntime needs libgomp (OpenMP).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# Bake the indra model into the HF cache (one download at build; none at run time).
RUN mkdir -p "$HF_HOME" && python - <<'PY'
import cv2
import numpy as np
import indra_ocr

cv2.imwrite("/tmp/warm.png", np.full((64, 128, 3), 255, dtype=np.uint8))
model = indra_ocr.load()
list(model.convert("/tmp/warm.png"))
print("indra model baked")
PY

# From here on the container must never reach HuggingFace (default-deny-egress cluster).
ENV HF_HUB_OFFLINE=1

RUN useradd -u 1000 -m appuser && chown -R appuser:appuser /opt/indra
USER 1000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
