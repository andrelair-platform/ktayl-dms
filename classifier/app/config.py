"""Runtime config (12-factor: all from the environment). Env-agnostic image — same artifact dev+prod."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # --- NATS (the trigger) ---
    nats_url: str = "nats://nats.messaging.svc:4222"
    nats_stream: str = "DMS_DOC"
    nats_subject: str = "dms.doc.consumed"
    nats_durable: str = "dms-classifier"

    # --- Paperless (read the doc + write the custom field/tag) ---
    paperless_url: str = "http://paperless:80"
    paperless_admin_user: str = "admin"
    paperless_admin_password: str = ""  # ESO paperless-secrets/admin-password → mint a token

    # --- indra OCR (in-ns) ---
    indra_ocr_url: str = "http://dms-indra-ocr:8000"

    # --- Presidio (SEC-01: mask PII before the LLM) ---
    presidio_analyzer_url: str = "http://presidio-analyzer.ai.svc.cluster.local:3000"
    presidio_anonymizer_url: str = "http://presidio-anonymizer.ai.svc.cluster.local:3000"

    # --- LiteLLM gateway + the model ---
    litellm_base_url: str = "http://litellm.ai.svc.cluster.local:4000"
    litellm_api_key: str = ""
    classifier_model: str = "tier-economy"

    # --- Langfuse (LLMOps) ---
    langfuse_host: str = "http://langfuse-web.ai.svc.cluster.local:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_prompt_label: str = "latest"  # dev=latest, prod=production
    environment: str = "development"

    # --- Systems of record (validate the candidate) — exact routes are deploy-time values ---
    claims_lookup_url: str = "http://ktayl-claims.ktayl-claims.svc:8080/api/claims"
    policy_lookup_url: str = "http://ktayl-core.ktayl-core.svc:8080/api/billing/policies"
    lookup_bearer: str = ""  # optional M2M bearer (SEC-03); empty on an open dev lookup

    # --- behaviour ---
    confidence_threshold: float = 0.7
    http_timeout_seconds: float = 30.0


settings = Settings()
