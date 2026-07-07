"""Application configuration loaded from environment and YAML."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
ENV_DIR = CONFIG_DIR / "environment"
DATA_DIR = ROOT_DIR / "data"
ENV_FILE = ENV_DIR / ".env"
EVALUATION_DIR = CONFIG_DIR / "evaluation"


def project_path(relative: str | Path) -> Path:
    """Resolve a path relative to the repository root."""
    return ROOT_DIR / relative


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o-mini"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_webhook_base_url: str = "http://localhost:8001"
    database_url: str = ""  # e.g., "postgresql://user:pass@host/db"

    chroma_persist_dir: str = "./data/chroma"
    chroma_server_url: str = ""  # e.g. "http://chroma-svc:8000" for HA client/server
    embedding_model: str = "text-embedding-3-small"

    crm_provider: str = "hubspot"
    hubspot_api_key: str = ""
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""

    webhook_signing_secret: str = ""
    settings_admin_token: str = ""
    integrations_encryption_key: str = ""

    jwt_secret: str = ""
    auth_required: bool = False
    rate_limit_rpm: int = 60

    slack_webhook_url: str = ""
    zendesk_api_key: str = ""
    zendesk_subdomain: str = ""
    servicenow_instance: str = ""
    servicenow_api_key: str = ""
    redis_url: str = ""
    sentry_dsn: str = ""
    otel_endpoint: str = ""

    # HashiCorp Vault (optional) — overrides env-based secrets
    vault_addr: str = ""
    vault_token: str = ""
    vault_path: str = "secret/data/nexus"

    # Logging sink: "stdout" (default), "file", or "loki"
    log_sink: str = "stdout"
    log_file: str = "logs/nexus.log"
    # Loki endpoint for log aggregation (e.g., http://loki:3100/loki/api/v1/push)
    loki_url: str = ""

    # Backup config
    backup_s3_bucket: str = ""
    backup_s3_prefix: str = "nexus-backups"
    backup_enabled: bool = False
    backup_cron: str = "0 3 * * *"  # daily at 3am

    app_host: str = "0.0.0.0"
    app_port: int = 8001
    log_level: str = "INFO"
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    return _merge_vault_credentials(settings)


def _fetch_hashivault_secrets(settings: Settings) -> dict[str, str]:
    """Optionally fetch secrets from HashiCorp Vault KV v2 engine."""
    if not settings.vault_addr or not settings.vault_token:
        return {}
    try:
        import hvac
        client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        secret = client.secrets.kv.v2.read_secret_version(path=settings.vault_path)
        return secret.get("data", {}).get("data", {})
    except ImportError:
        logger.warning("hvac_not_installed_vault_secrets_skipped")
        return {}
    except Exception as exc:
        logger.warning("vault_fetch_failed", error=str(exc))
        return {}


def _merge_vault_credentials(settings: Settings) -> Settings:
    """Overlay encrypted vault credentials onto environment settings.

    Order of precedence (later wins):
      1. .env file
      2. Fernet encrypted vault (local)
      3. HashiCorp Vault (remote, if configured)
    """
    try:
        from src.integrations.secrets_vault import CREDENTIAL_KEYS, get_secrets_vault
        vault_creds = get_secrets_vault().get_credentials()
        for key in CREDENTIAL_KEYS:
            value = vault_creds.get(key)
            if value:
                setattr(settings, key, value)
    except Exception as exc:
        logger.warning("vault_merge_failed", error=str(exc))

    # HashiCorp Vault overlay (takes precedence)
    hc_vault = _fetch_hashivault_secrets(settings)
    for key, value in hc_vault.items():
        if value and hasattr(settings, key):
            setattr(settings, key, value)
            logger.debug("vault_secret_loaded", key=key)

    return settings


def reload_settings() -> Settings:
    get_settings.cache_clear()
    try:
        from src.integrations.secrets_vault import reload_secrets_vault

        reload_secrets_vault()
    except Exception as exc:
        logger.warning("vault_reload_failed", error=str(exc))
    return get_settings()


def load_agent_config() -> dict[str, Any]:
    config_path = CONFIG_DIR / "agents.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)
