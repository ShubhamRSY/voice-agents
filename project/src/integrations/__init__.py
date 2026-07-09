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
from src.integrations.dynamics365 import Dynamics365Client
from src.integrations.copper import CopperClient
from src.integrations.marketo import MarketoClient
from src.integrations.klaviyo import KlaviyoClient
from src.integrations.guru import GuruClient
from src.integrations.document360 import Document360Client
from src.integrations.five9 import Five9Client
from src.integrations.genesys import GenesysClient
from src.integrations.nice import NiceClient
from src.integrations.zoom import ZoomClient
from src.integrations.vonage import VonageClient
from src.integrations.dialpad import DialpadClient
from src.integrations.aircall import AircallClient
from src.integrations.workday import WorkdayClient
from src.integrations.adp import ADPClient
from src.integrations.tableau import TableauClient
from src.integrations.powerbi import PowerBIClient
from src.integrations.creatio import CreatioClient
from src.integrations.salesloft import SalesloftClient
from src.integrations.sharepoint import SharePointClient
from src.integrations.talkdesk import TalkdeskClient
from src.integrations.ujet import UjetClient
from src.integrations.eight_by_eight import EightByEightClient
from src.integrations.gusto import GustoClient
from src.integrations.epic import EpicClient

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
    "Dynamics365Client",
    "CopperClient",
    "MarketoClient",
    "KlaviyoClient",
    "GuruClient",
    "Document360Client",
    "Five9Client",
    "GenesysClient",
    "NiceClient",
    "ZoomClient",
    "VonageClient",
    "DialpadClient",
    "AircallClient",
    "WorkdayClient",
    "ADPClient",
    "TableauClient",
    "PowerBIClient",
    "CreatioClient",
    "SalesloftClient",
    "SharePointClient",
    "TalkdeskClient",
    "UjetClient",
    "EightByEightClient",
    "GustoClient",
    "EpicClient",
    "IntegrationRouter",
    "SecretsVault",
    "WebhookDispatcher",
    "get_secrets_vault",
    "mask_secret",
]
