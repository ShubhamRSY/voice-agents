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
from src.integrations.pagerduty import PagerDutyClient
from src.integrations.linear import LinearClient
from src.integrations.bigquery import BigQueryClient
from src.integrations.help_scout import HelpScoutClient
from src.integrations.clickup import ClickUpClient
from src.integrations.trello import TrelloClient
from src.integrations.front import FrontClient
from src.integrations.amplitude import AmplitudeClient
from src.integrations.azure_devops import AzureDevOpsClient
from src.integrations.shopify import ShopifyClient
from src.integrations.stripe_integration import StripeClient
from src.integrations.mailchimp import MailchimpClient
from src.integrations.zoho_crm import ZohoCRMClient
from src.integrations.bamboohr import BambooHRClient
from src.integrations.ringcentral import RingCentralClient
from src.integrations.confluence import ConfluenceClient

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
    "PagerDutyClient",
    "LinearClient",
    "BigQueryClient",
    "HelpScoutClient",
    "ClickUpClient",
    "TrelloClient",
    "FrontClient",
    "AmplitudeClient",
    "AzureDevOpsClient",
    "ShopifyClient",
    "StripeClient",
    "MailchimpClient",
    "ZohoCRMClient",
    "BambooHRClient",
    "RingCentralClient",
    "ConfluenceClient",
    "IntegrationRouter",
    "SecretsVault",
    "WebhookDispatcher",
    "get_secrets_vault",
    "mask_secret",
]
