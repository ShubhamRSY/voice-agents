"""External system integrations."""

from src.integrations.crm import CRMClient, HubSpotClient
from src.integrations.secrets_vault import SecretsVault, get_secrets_vault, mask_secret
from src.integrations.webhooks import IntegrationRouter, WebhookDispatcher
from src.integrations.freshdesk import FreshdeskClient
from src.integrations.intercom import IntercomClient
from src.integrations.asana import AsanaClient
from src.integrations.monday import MondayClient
from src.integrations.notion import NotionClient
from src.integrations.github import GitHubClient
from src.integrations.teams import TeamsClient
from src.integrations.pipedrive import PipedriveClient
from src.integrations.snowflake import SnowflakeClient

__all__ = [
    "CRMClient",
    "HubSpotClient",
    "FreshdeskClient",
    "IntercomClient",
    "AsanaClient",
    "MondayClient",
    "NotionClient",
    "GitHubClient",
    "TeamsClient",
    "PipedriveClient",
    "SnowflakeClient",
    "IntegrationRouter",
    "SecretsVault",
    "WebhookDispatcher",
    "get_secrets_vault",
    "mask_secret",
]
