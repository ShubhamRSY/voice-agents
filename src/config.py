"""Application configuration loaded from environment and YAML."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
EVALUATION_DIR = CONFIG_DIR / "evaluation"
ENV_DIR = CONFIG_DIR / "environment"
DOCS_DIR = ROOT_DIR / "docs"
DATA_DIR = ROOT_DIR / "data"
ENV_FILE = ENV_DIR / ".env"
ENV_EXAMPLE_FILE = ENV_DIR / ".env.example"
DEPS_DIR = CONFIG_DIR / "deps"
DEPLOY_DIR = ROOT_DIR / "deploy"


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
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o-mini"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_webhook_base_url: str = "http://localhost:8000"

    chroma_persist_dir: str = "./data/chroma"
    embedding_model: str = "text-embedding-3-small"

    crm_provider: str = "hubspot"
    hubspot_api_key: str = ""
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""

    webhook_signing_secret: str = ""
    settings_admin_token: str = ""
    integrations_encryption_key: str = ""

    jwt_secret: str = ""
    rate_limit_rpm: int = 60

    slack_webhook_url: str = ""
    zendesk_api_key: str = ""
    zendesk_subdomain: str = ""
    servicenow_instance: str = ""
    servicenow_api_key: str = ""
    redis_url: str = ""
    sentry_dsn: str = ""
    otel_endpoint: str = ""

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    return _merge_vault_credentials(settings)


def _merge_vault_credentials(settings: Settings) -> Settings:
    """Overlay encrypted vault credentials onto environment settings."""
    try:
        from src.integrations.secrets_vault import CREDENTIAL_KEYS, get_secrets_vault

        vault_creds = get_secrets_vault().get_credentials()
        for key in CREDENTIAL_KEYS:
            value = vault_creds.get(key)
            if value:
                setattr(settings, key, value)
    except Exception:
        pass
    return settings


def reload_settings() -> Settings:
    get_settings.cache_clear()
    try:
        from src.integrations.secrets_vault import reload_secrets_vault

        reload_secrets_vault()
    except Exception:
        pass
    return get_settings()


def load_agent_config() -> dict[str, Any]:
    config_path = CONFIG_DIR / "agents.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)
