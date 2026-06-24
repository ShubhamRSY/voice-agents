"""Tests for encrypted integrations vault."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.integrations.secrets_vault import SecretsVault, mask_secret


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "integrations.vault"


@pytest.fixture
def vault(vault_path: Path) -> SecretsVault:
    key = Fernet.generate_key()
    return SecretsVault(path=vault_path, key=key)


class TestSecretsVault:
    def test_encrypts_credentials_at_rest(self, vault: SecretsVault, vault_path: Path):
        key = Fernet.generate_key()
        vault = SecretsVault(path=vault_path, key=key)
        vault.set_credential("openai_api_key", "sk-test-secret-key-12345")
        raw = vault_path.read_bytes()
        assert b"sk-test-secret-key" not in raw

        reloaded = SecretsVault(path=vault_path, key=key)
        assert reloaded.get_credentials()["openai_api_key"] == "sk-test-secret-key-12345"

    def test_clear_credential(self, vault: SecretsVault):
        vault.set_credential("hubspot_api_key", "pat-123")
        vault.clear_credential("hubspot_api_key")
        assert "hubspot_api_key" not in vault.get_credentials()

    def test_persists_webhooks(self, vault: SecretsVault, vault_path: Path):
        key = Fernet.generate_key()
        vault = SecretsVault(path=vault_path, key=key)
        vault.set_webhook("conversation.started", "https://hooks.zapier.com/hooks/catch/abc")
        reloaded = SecretsVault(path=vault_path, key=key)
        assert reloaded.get_webhooks()["conversation.started"].startswith("https://hooks.zapier.com")

    def test_credential_status_prefers_vault_over_env(self, vault: SecretsVault):
        status = vault.credential_status({"openai_api_key": "sk-env-key"})
        assert status["openai_api_key"]["source"] == "env"
        assert status["openai_api_key"]["configured"]

        vault.set_credential("openai_api_key", "sk-vault-key-abcdef")
        status = vault.credential_status({"openai_api_key": "sk-env-key"})
        assert status["openai_api_key"]["source"] == "vault"
        assert status["openai_api_key"]["configured"]


class TestMaskSecret:
    def test_masks_long_values(self):
        assert mask_secret("sk-proj-abcdefghijklmnop") == "sk-p••••mnop"

    def test_empty_value(self):
        assert mask_secret("") == ""
