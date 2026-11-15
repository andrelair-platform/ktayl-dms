# indra OCR service — CPU-only, self-hosted (ADR-002). The ~76 MB model is BAKED into the image
# because the runtime cluster is default-deny-egress (no HuggingFace fetch at run time).
FROM python:3.12-slim

ENV INDRA_OCR_MODEL_DIR=/opt/indra/models \
    HF_HOME=/opt/indra/hf \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# opencv-python-headless still needs libglib at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# Bake the indra model into the image (one download at build; none at run time).
RUN mkdir -p "$INDRA_OCR_MODEL_DIR" "$HF_HOME" && python - <<'PY'
import cv2
import numpy as np
import indra_ocr

cv2.imwrite("/tmp/warm.png", np.full((64, 128, 3), 255, dtype=np.uint8))
model = indra_ocr.load()
list(model.convert("/tmp/warm.png"))
print("indra model baked")
PY

RUN useradd -u 1000 -m appuser && chown -R appuser:appuser /opt/indra
USER 1000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
