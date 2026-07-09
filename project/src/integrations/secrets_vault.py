"""Encrypted storage for integration credentials and webhook URLs."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken

from src.config import DATA_DIR

logger = structlog.get_logger()

VAULT_FILE = DATA_DIR / "integrations.vault"
VAULT_KEY_FILE = DATA_DIR / ".vault_key"
KEY_ENV = "INTEGRATIONS_ENCRYPTION_KEY"

CREDENTIAL_KEYS = (
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_phone_number",
    "twilio_webhook_base_url",
    "hubspot_api_key",
    "salesforce_client_id",
    "salesforce_client_secret",
    "webhook_signing_secret",
    "freshdesk_domain",
    "freshdesk_api_key",
    "intercom_access_token",
    "asana_access_token",
    "monday_api_key",
    "notion_api_key",
    "github_token",
    "github_repo",
    "teams_webhook_url",
    "pipedrive_api_token",
    "pipedrive_domain",
    "snowflake_account",
    "snowflake_user",
    "snowflake_password",
    "snowflake_warehouse",
    "snowflake_database",
    "snowflake_schema",
)

WEBHOOK_EVENTS = (
    "conversation.started",
    "conversation.ended",
    "ticket.created",
    "conversation.escalated",
)


def mask_secret(value: str, *, visible: int = 4) -> str:
    """Return a masked preview of a secret for API responses."""
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "••••••••"
    return f"{value[:visible]}••••{value[-visible:]}"


class SecretsVault:
    """Fernet-encrypted JSON vault for credentials and webhook URLs."""

    def __init__(self, path: Path | None = None, key: str | bytes | None = None):
        self.path = path or VAULT_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._resolve_key(key))
        self._data = self._load()

    @staticmethod
    def _resolve_key(explicit: str | bytes | None) -> bytes:
        if explicit:
            return explicit if isinstance(explicit, bytes) else explicit.encode()

        env_key = os.environ.get(KEY_ENV, "").strip()
        if not env_key:
            from dotenv import dotenv_values

            from src.config import ENV_FILE

            if ENV_FILE.exists():
                env_key = (dotenv_values(ENV_FILE).get(KEY_ENV) or "").strip()

        if env_key:
            return env_key.encode()

        if VAULT_KEY_FILE.exists():
            return VAULT_KEY_FILE.read_text(encoding="utf-8").strip().encode()

        generated = Fernet.generate_key()
        VAULT_KEY_FILE.write_text(generated.decode(), encoding="utf-8")
        VAULT_KEY_FILE.chmod(0o600)
        logger.warning(
            "vault_key_generated",
            path=str(VAULT_KEY_FILE),
            hint=f"Set {KEY_ENV} in production for a stable encryption key.",
        )
        return generated

    def _empty_payload(self) -> dict[str, Any]:
        return {"credentials": {}, "webhooks": {}}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_payload()

        try:
            raw = self.path.read_bytes()
            if not raw:
                return self._empty_payload()
            decrypted = self._fernet.decrypt(raw)
            data = json.loads(decrypted.decode("utf-8"))
            if not isinstance(data, dict):
                return self._empty_payload()
            data.setdefault("credentials", {})
            data.setdefault("webhooks", {})
            return data
        except (InvalidToken, json.JSONDecodeError, ValueError) as exc:
            logger.error("vault_load_failed", error=str(exc))
            return self._empty_payload()

    def _save(self) -> None:
        payload = json.dumps(self._data, separators=(",", ":")).encode("utf-8")
        encrypted = self._fernet.encrypt(payload)
        self.path.write_bytes(encrypted)
        self.path.chmod(0o600)

    def get_credentials(self) -> dict[str, str]:
        creds = self._data.get("credentials", {})
        return {key: str(creds[key]) for key in CREDENTIAL_KEYS if creds.get(key)}

    def get_webhooks(self) -> dict[str, str]:
        hooks = self._data.get("webhooks", {})
        return {event: str(url) for event, url in hooks.items() if url}

    def set_credential(self, key: str, value: str | None) -> None:
        if key not in CREDENTIAL_KEYS:
            raise ValueError(f"Unsupported credential key: {key}")
        creds = self._data.setdefault("credentials", {})
        if value:
            creds[key] = value
        else:
            creds.pop(key, None)
        self._save()

    def set_credentials(self, updates: dict[str, str | None]) -> None:
        for key, value in updates.items():
            if key not in CREDENTIAL_KEYS:
                raise ValueError(f"Unsupported credential key: {key}")
            self.set_credential(key, value if value else None)

    def clear_credential(self, key: str) -> None:
        self.set_credential(key, None)

    def clear_all_credentials(self) -> None:
        self._data["credentials"] = {}
        self._save()

    def set_webhook(self, event_type: str, url: str | None) -> None:
        hooks = self._data.setdefault("webhooks", {})
        if url:
            hooks[event_type] = url
        else:
            hooks.pop(event_type, None)
        self._save()

    def clear_webhook(self, event_type: str) -> None:
        self.set_webhook(event_type, None)

    def clear_all_webhooks(self) -> None:
        self._data["webhooks"] = {}
        self._save()

    def credential_status(self, env_values: dict[str, str]) -> dict[str, dict[str, Any]]:
        vault_creds = self.get_credentials()
        status: dict[str, dict[str, Any]] = {}
        for key in CREDENTIAL_KEYS:
            vault_val = vault_creds.get(key, "")
            env_val = env_values.get(key, "")
            active = vault_val or env_val
            if vault_val:
                source = "vault"
                masked = mask_secret(vault_val)
            elif env_val:
                source = "env"
                masked = mask_secret(env_val)
            else:
                source = "none"
                masked = ""
            status[key] = {
                "configured": bool(active),
                "source": source,
                "masked": masked,
            }
        return status

    def webhook_status(self) -> dict[str, dict[str, Any]]:
        hooks = self.get_webhooks()
        return {
            event: {
                "configured": event in hooks,
                "masked": mask_secret(hooks[event], visible=8) if event in hooks else "",
            }
            for event in WEBHOOK_EVENTS
        }

    def diagnostics(self) -> dict[str, Any]:
        """Report whether the vault file can be decrypted with the current key."""
        exists = self.path.exists()
        decrypt_ok = True
        key_source = "generated"
        if os.environ.get(KEY_ENV, "").strip():
            key_source = "env"
        elif VAULT_KEY_FILE.exists():
            key_source = "file"

        if exists:
            try:
                raw = self.path.read_bytes()
                if raw:
                    self._fernet.decrypt(raw)
            except InvalidToken:
                decrypt_ok = False

        return {
            "path": str(self.path),
            "file_exists": exists,
            "decrypt_ok": decrypt_ok,
            "key_source": key_source,
            "operational": (not exists) or decrypt_ok,
        }


@lru_cache
def get_secrets_vault() -> SecretsVault:
    return SecretsVault()


def reload_secrets_vault() -> SecretsVault:
    get_secrets_vault.cache_clear()
    return get_secrets_vault()
