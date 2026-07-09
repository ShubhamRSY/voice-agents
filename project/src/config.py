"""Application configuration loaded from environment and YAML."""

import os
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
HF_CACHE_DIR = DATA_DIR / "hf_cache"


def _path_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def ensure_hf_cache() -> Path:
    """Point HuggingFace caches at a writable project directory.

    Fixes broken placeholders like ``/Volumes/<YourDriveName>`` in .env that
    cause PermissionError when sentence-transformers downloads models.
    """
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    default = str(HF_CACHE_DIR)
    for var in ("HF_HOME", "SENTENCE_TRANSFORMERS_HOME", "TRANSFORMERS_CACHE", "HUGGINGFACE_HUB_CACHE"):
        raw = os.environ.get(var, "").strip()
        if not raw or "<" in raw or ">" in raw or not _path_is_writable(Path(raw)):
            if raw and ("<" in raw or ">" in raw):
                logger.warning("hf_cache_path_invalid", variable=var, path=raw, fallback=default)
            os.environ[var] = default
    return HF_CACHE_DIR


# Run before any sentence-transformers / huggingface_hub import.
ensure_hf_cache()


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
    # When false, /auth/register is closed after the first admin exists.
    # First-user bootstrap is always allowed so production can be set up.
    allow_registration: bool = False
    demo_mode: bool = False
    app_env: str = "development"
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

    # --- OIDC SSO (enterprise auth) ---
    oidc_enabled: bool = False
    # Issuer base URL, e.g. https://YOUR_DOMAIN/ (Auth0) or https://login.microsoftonline.com/<tenant>/v2.0
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    # Where the IdP redirects back (must match provider config)
    oidc_redirect_uri: str = ""
    # Space-separated scopes, must include openid email
    oidc_scopes: str = "openid profile email"
    # Provisioning defaults
    oidc_default_tenant_id: str = "default"
    oidc_default_role: str = "agent"
    # Comma-separated admin email domains; matching users get admin role
    oidc_admin_domains: str = ""

    # Email channel (SMTP outbound)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # Meta Messenger / Instagram
    meta_page_access_token: str = ""
    meta_verify_token: str = ""
    meta_app_secret: str = ""

    # Zendesk (also in vault)
    # zendesk_api_key, zendesk_subdomain already above

    # Jira
    jira_base_url: str = ""
    jira_user_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "SUP"

    # Freshdesk
    freshdesk_domain: str = ""
    freshdesk_api_key: str = ""

    # Intercom
    intercom_access_token: str = ""

    # Asana
    asana_access_token: str = ""

    # Monday.com
    monday_api_key: str = ""

    # Notion
    notion_api_key: str = ""

    # GitHub
    github_token: str = ""
    github_repo: str = ""

    # Microsoft Teams
    teams_webhook_url: str = ""

    # Pipedrive
    pipedrive_api_token: str = ""
    pipedrive_domain: str = ""

    # Snowflake
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = ""
    snowflake_schema: str = "PUBLIC"

    # Guest demo sandbox on login screen
    allow_guest_demo: bool = True

    # Multi-region HA
    primary_region: str = "us-east-1"
    secondary_region: str = ""
    ha_failover_enabled: bool = False
    database_read_replica_url: str = ""
    ha_peer_health_url: str = ""

    # Compliance mode flags
    hipaa_mode: bool = False

    # Nexus Cloud SaaS
    saas_signup_enabled: bool = True
    app_public_url: str = "http://localhost:8001"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"


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
