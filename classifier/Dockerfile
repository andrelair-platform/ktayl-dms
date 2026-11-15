# DMS document classifier — a NATS JetStream worker (no model baked; all collaborators are remote).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY prompts ./prompts
RUN pip install .

RUN useradd -u 1000 -m appuser
USER 1000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
