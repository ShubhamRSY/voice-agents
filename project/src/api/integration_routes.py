"""Integration vault, webhooks, and enterprise platform connectors."""

from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi import Depends
from structlog import get_logger

from src.auth import AuthContext, require_admin
from src.config import get_settings, reload_settings
from src.integrations.secrets_vault import CREDENTIAL_KEYS, WEBHOOK_EVENTS, get_secrets_vault
from src.integrations.slack import SlackNotifier
from src.integrations.zendesk import ZendeskClient
from src.integrations.servicenow import ServiceNowClient
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
from src.integrations.catalog import CATEGORY_LABELS, TIER_LABELS, catalog_summary, get_catalog
from src.api.deps import (
    CredentialsUpdateRequest, WebhookRegisterRequest,
    integration_router, require_settings_token, env_credentials,
)

logger = get_logger()
router = APIRouter()


@router.get("/integrations/catalog")
async def integrations_catalog(
    category: str = "all",
    tier: str = "all",
    q: str = "",
) -> dict[str, Any]:
    """Public integration catalog with honest native / webhook / roadmap tiers."""
    settings = get_settings()
    providers = (await integrations_status())["providers"]
    native_configured = {
        "servicenow": bool(settings.servicenow_instance and settings.servicenow_api_key),
        "slack": bool(settings.slack_webhook_url),
    }
    items = []
    for item in get_catalog(category=category or None, tier=tier or None, q=q or None):
        entry = dict(item)
        provider_key = item.get("provider_key")
        if provider_key and provider_key in providers:
            entry["configured"] = bool(providers[provider_key].get("configured"))
            entry["features"] = providers[provider_key].get("features", [])
        elif item["id"] in native_configured:
            entry["configured"] = native_configured[item["id"]]
        else:
            entry["configured"] = False
        items.append(entry)
    return {
        "summary": catalog_summary(),
        "category_labels": CATEGORY_LABELS,
        "tier_labels": TIER_LABELS,
        "items": items,
        "security": {
            "vault_encryption": True,
            "webhook_signing": bool(settings.webhook_signing_secret),
            "hipaa_mode": settings.hipaa_mode,
        },
    }


@router.get("/integrations/status")
async def integrations_status() -> dict[str, Any]:
    settings = get_settings()
    vault = get_secrets_vault()
    vault_diag = vault.diagnostics()
    creds = vault.credential_status(env_credentials())
    hooks = vault.webhook_status()

    return {
        "encryption": {
            "enabled": vault_diag["file_exists"],
            "operational": vault_diag["operational"],
            "decrypt_ok": vault_diag["decrypt_ok"],
            "vault_path": vault_diag["path"],
            "key_source": vault_diag["key_source"],
        },
        "providers": {
            "openai": {
                "configured": creds["openai_api_key"]["configured"],
                "source": creds["openai_api_key"]["source"],
                "masked_key": creds["openai_api_key"]["masked"],
                "features": ["llm", "embeddings", "stt", "tts"],
            },
            "anthropic": {
                "configured": creds["anthropic_api_key"]["configured"],
                "source": creds["anthropic_api_key"]["source"],
                "masked_key": creds["anthropic_api_key"]["masked"],
                "features": ["llm"],
            },
            "gemini": {
                "configured": creds["gemini_api_key"]["configured"],
                "source": creds["gemini_api_key"]["source"],
                "masked_key": creds["gemini_api_key"]["masked"],
                "features": ["llm"],
            },
            "twilio": {
                "configured": all(
                    creds[key]["configured"]
                    for key in ("twilio_account_sid", "twilio_auth_token", "twilio_phone_number")
                ),
                "masked_sid": creds["twilio_account_sid"]["masked"],
                "masked_phone": creds["twilio_phone_number"]["masked"],
                "webhook_base_url": creds["twilio_webhook_base_url"]["masked"] or None,
                "source": "vault" if vault.get_credentials().get("twilio_account_sid") else (
                    "env" if env_credentials().get("twilio_account_sid") else "none"
                ),
                "features": ["pstn", "voice_webhooks", "whatsapp", "sms"],
            },
            "hubspot": {
                "configured": creds["hubspot_api_key"]["configured"],
                "source": creds["hubspot_api_key"]["source"],
                "masked_key": creds["hubspot_api_key"]["masked"],
                "features": ["crm_lookup", "ticket_sync"],
            },
            "salesforce": {
                "configured": creds["salesforce_client_id"]["configured"],
                "source": creds["salesforce_client_id"]["source"],
                "masked_key": creds["salesforce_client_id"]["masked"],
                "features": ["crm_lookup", "case_management"],
            },
            "whatsapp": {
                "configured": all(
                    creds[key]["configured"]
                    for key in ("twilio_account_sid", "twilio_auth_token", "twilio_phone_number")
                ),
                "features": ["messaging", "inbound_webhook"],
            },
            "zendesk": {
                "configured": bool(settings.zendesk_api_key and settings.zendesk_subdomain),
                "features": ["ticket_sync", "contact_search"],
            },
            "jira": {
                "configured": bool(settings.jira_base_url and settings.jira_api_token),
                "features": ["issue_sync"],
            },
            "freshdesk": {
                "configured": bool(settings.freshdesk_domain and settings.freshdesk_api_key),
                "features": ["ticket_sync", "contact_search"],
            },
            "intercom": {
                "configured": bool(settings.intercom_access_token),
                "features": ["conversations", "contact_search"],
            },
            "asana": {
                "configured": bool(settings.asana_access_token),
                "features": ["task_sync", "project_search"],
            },
            "monday": {
                "configured": bool(settings.monday_api_key),
                "features": ["item_sync", "board_management"],
            },
            "notion": {
                "configured": bool(settings.notion_api_key),
                "features": ["page_sync", "search"],
            },
            "github": {
                "configured": bool(settings.github_token and settings.github_repo),
                "features": ["issue_sync", "comments"],
            },
            "teams": {
                "configured": bool(settings.teams_webhook_url),
                "features": ["channel_alerts", "escalations"],
            },
            "pipedrive": {
                "configured": bool(settings.pipedrive_api_token),
                "features": ["deal_sync", "contact_search"],
            },
            "snowflake": {
                "configured": bool(
                    settings.snowflake_account
                    and settings.snowflake_user
                    and settings.snowflake_password
                    and settings.snowflake_warehouse
                    and settings.snowflake_database
                ),
                "features": ["sql_execute", "conversation_events"],
            },
            "pagerduty": {
                "configured": bool(settings.pagerduty_api_key),
                "features": ["incident_create", "on_call_alerts"],
            },
            "linear": {
                "configured": bool(settings.linear_api_key),
                "features": ["issue_sync"],
            },
            "bigquery": {
                "configured": bool(
                    settings.bigquery_project_id
                    and settings.bigquery_dataset_id
                    and settings.bigquery_table_id
                    and settings.bigquery_access_token
                ),
                "features": ["row_insert", "conversation_events"],
            },
            "help_scout": {
                "configured": bool(settings.help_scout_api_key),
                "features": ["conversation_sync", "shared_inbox"],
            },
            "clickup": {
                "configured": bool(settings.clickup_api_token),
                "features": ["task_sync"],
            },
            "trello": {
                "configured": bool(settings.trello_api_key and settings.trello_api_token),
                "features": ["card_sync", "kanban"],
            },
            "front": {
                "configured": bool(settings.front_api_token),
                "features": ["inbox_sync", "message_send"],
            },
            "amplitude": {
                "configured": bool(settings.amplitude_api_key),
                "features": ["event_tracking", "analytics"],
            },
            "azure_devops": {
                "configured": bool(settings.azure_devops_org and settings.azure_devops_project and settings.azure_devops_pat),
                "features": ["work_item_sync"],
            },
            "shopify": {
                "configured": bool(settings.shopify_shop_domain and settings.shopify_access_token),
                "features": ["customer_lookup", "order_context"],
            },
            "stripe": {
                "configured": bool(settings.stripe_secret_key),
                "features": ["customer_lookup", "billing_context"],
            },
            "mailchimp": {
                "configured": bool(settings.mailchimp_api_key),
                "features": ["list_sync", "subscriber_add"],
            },
            "zoho": {
                "configured": bool(settings.zoho_access_token),
                "features": ["lead_sync", "crm_lookup"],
            },
            "bamboohr": {
                "configured": bool(settings.bamboohr_subdomain and settings.bamboohr_api_key),
                "features": ["employee_lookup", "hris_context"],
            },
            "ringcentral": {
                "configured": bool(settings.ringcentral_webhook_url),
                "features": ["telephony_alerts"],
            },
            "confluence": {
                "configured": bool(settings.confluence_base_url and settings.confluence_api_token),
                "features": ["page_sync", "knowledge_base"],
            },
            "dynamics": {
                "configured": bool(settings.dynamics_instance_url and settings.dynamics_access_token),
                "features": ["case_sync", "crm_lookup"],
            },
            "copper": {
                "configured": bool(settings.copper_api_key and settings.copper_user_email),
                "features": ["lead_sync"],
            },
            "marketo": {
                "configured": bool(settings.marketo_client_id and settings.marketo_client_secret and settings.marketo_base_url),
                "features": ["lead_capture"],
            },
            "klaviyo": {
                "configured": bool(settings.klaviyo_api_key),
                "features": ["event_tracking"],
            },
            "guru": {
                "configured": bool(settings.guru_api_token),
                "features": ["card_sync", "knowledge"],
            },
            "document360": {
                "configured": bool(settings.document360_api_token and settings.document360_base_url),
                "features": ["article_sync"],
            },
            "five9": {
                "configured": bool(settings.five9_webhook_url or (settings.five9_api_username and settings.five9_api_password)),
                "features": ["disposition_sync"],
            },
            "genesys": {
                "configured": bool(settings.genesys_api_key),
                "features": ["callback_sync"],
            },
            "nice": {
                "configured": bool(settings.nice_api_key),
                "features": ["contact_sync"],
            },
            "zoom": {
                "configured": bool(settings.zoom_webhook_url or settings.zoom_client_id),
                "features": ["notifications"],
            },
            "vonage": {
                "configured": bool(settings.vonage_api_key and settings.vonage_api_secret),
                "features": ["sms"],
            },
            "dialpad": {
                "configured": bool(settings.dialpad_api_key),
                "features": ["sms"],
            },
            "aircall": {
                "configured": bool(settings.aircall_api_id and settings.aircall_api_token),
                "features": ["contact_sync"],
            },
            "workday": {
                "configured": bool(settings.workday_tenant and settings.workday_username and settings.workday_password),
                "features": ["worker_lookup"],
            },
            "adp": {
                "configured": bool(settings.adp_client_id and settings.adp_client_secret),
                "features": ["worker_lookup"],
            },
            "tableau": {
                "configured": bool(settings.tableau_server_url and settings.tableau_token_name and settings.tableau_token_secret),
                "features": ["analytics_push"],
            },
            "powerbi": {
                "configured": bool(settings.powerbi_access_token and settings.powerbi_dataset_id),
                "features": ["dataset_push"],
            },
            "creatio": {
                "configured": bool(settings.creatio_base_url and settings.creatio_username and settings.creatio_password),
                "features": ["lead_sync"],
            },
            "salesloft": {
                "configured": bool(settings.salesloft_api_key),
                "features": ["person_sync"],
            },
            "sharepoint": {
                "configured": bool(settings.sharepoint_site_url and settings.sharepoint_access_token),
                "features": ["list_sync"],
            },
            "talkdesk": {
                "configured": bool(settings.talkdesk_api_token),
                "features": ["contact_sync"],
            },
            "ujet": {
                "configured": bool(settings.ujet_api_key and settings.ujet_subdomain),
                "features": ["callback_sync"],
            },
            "eight_by_eight": {
                "configured": bool(settings.eight_by_eight_api_key or settings.eight_by_eight_webhook_url),
                "features": ["telephony_alerts"],
            },
            "gusto": {
                "configured": bool(settings.gusto_access_token and settings.gusto_company_id),
                "features": ["employee_lookup"],
            },
            "epic": {
                "configured": bool(settings.epic_fhir_base_url and settings.epic_fhir_access_token),
                "features": ["patient_lookup", "fhir"],
            },
            "meta": {
                "configured": bool(settings.meta_page_access_token),
                "features": ["messenger", "instagram", "inbound_webhook"],
            },
            "ipaas": {
                "configured": any(item["configured"] for item in hooks.values()),
                "webhook_signing": creds["webhook_signing_secret"]["configured"],
                "masked_signing_secret": creds["webhook_signing_secret"]["masked"],
                "events": hooks,
                "features": ["n8n", "zapier"],
            },
        },
        "mock_mode": not bool(settings.openai_api_key or settings.anthropic_api_key),
    }


@router.put("/integrations/credentials")
async def save_credentials(
    request: Request,
    body: CredentialsUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    require_settings_token(request)
    vault = get_secrets_vault()
    updates = body.model_dump(exclude_unset=True)
    vault.set_credentials(updates)
    from src.database import db
    db.log_audit(ctx.tenant_id, ctx.user_id, "integrations.credentials.updated", "integrations", {"updated": list(updates.keys())})
    reload_settings()
    integration_router.load_from_vault()
    return {
        "status": "saved",
        "updated": list(updates.keys()),
        "providers": (await integrations_status())["providers"],
    }


@router.delete("/integrations/credentials/{credential_key}")
async def delete_credential(
    request: Request,
    credential_key: str,
    ctx: AuthContext = Depends(require_admin),
) -> dict[str, str]:
    require_settings_token(request)
    if credential_key not in CREDENTIAL_KEYS:
        raise HTTPException(status_code=400, detail=f"Unsupported credential: {credential_key}")
    get_secrets_vault().clear_credential(credential_key)
    from src.database import db
    db.log_audit(ctx.tenant_id, ctx.user_id, "integrations.credential.cleared", "integrations", {"credential": credential_key})
    reload_settings()
    integration_router.load_from_vault()
    return {"status": "cleared", "credential": credential_key}


@router.post("/integrations/webhooks")
async def register_webhook(
    request: Request,
    body: WebhookRegisterRequest,
    ctx: AuthContext = Depends(require_admin),
) -> dict[str, str]:
    require_settings_token(request)
    if body.event_type not in WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {body.event_type}")
    integration_router.register_webhook(body.event_type, body.url)
    from src.database import db
    db.log_audit(ctx.tenant_id, ctx.user_id, "integrations.webhook.registered", "integrations", {"event_type": body.event_type, "url": body.url})
    return {"status": "registered", "event_type": body.event_type}


@router.delete("/integrations/webhooks/{event_type}")
async def delete_webhook(
    request: Request,
    event_type: str,
    ctx: AuthContext = Depends(require_admin),
) -> dict[str, str]:
    require_settings_token(request)
    if event_type not in WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {event_type}")
    integration_router.unregister_webhook(event_type)
    from src.database import db
    db.log_audit(ctx.tenant_id, ctx.user_id, "integrations.webhook.removed", "integrations", {"event_type": event_type})
    return {"status": "removed", "event_type": event_type}


@router.post("/integrations/zendesk/ticket")
async def zendesk_create_ticket(subject: str, description: str, requester_email: str = "") -> dict:
    client = ZendeskClient()
    return await client.create_ticket(subject, description, requester_email)


@router.post("/integrations/servicenow/incident")
async def servicenow_create_incident(short_description: str, description: str, caller_email: str = "") -> dict:
    client = ServiceNowClient()
    return await client.create_incident(short_description, description, caller_email)


@router.post("/integrations/slack/alert")
async def slack_send_alert(text: str, channel: str = "#general") -> dict:
    notifier = SlackNotifier()
    return await notifier.send_alert(channel, text)


@router.post("/integrations/freshdesk/ticket")
async def freshdesk_create_ticket(subject: str, description: str, email: str = "", priority: int = 2) -> dict:
    client = FreshdeskClient()
    return await client.create_ticket(subject, description, email, priority)


@router.post("/integrations/intercom/conversation")
async def intercom_create_conversation(subject: str, body: str, email: str) -> dict:
    client = IntercomClient()
    return await client.create_conversation(subject, body, email)


@router.post("/integrations/asana/task")
async def asana_create_task(name: str, notes: str = "", project_gid: str = "", assignee: str = "") -> dict:
    client = AsanaClient()
    return await client.create_task(name, notes, project_gid, assignee)


@router.post("/integrations/monday/item")
async def monday_create_item(board_id: int, name: str) -> dict:
    client = MondayClient()
    return await client.create_item(board_id, name)


@router.post("/integrations/notion/page")
async def notion_create_page(parent_page_id: str, title: str, content: str = "") -> dict:
    client = NotionClient()
    return await client.create_page(parent_page_id, title, content)


@router.post("/integrations/github/issue")
async def github_create_issue(title: str, body: str = "", labels: str = "") -> dict:
    client = GitHubClient()
    label_list = [label.strip() for label in labels.split(",") if label.strip()] if labels else None
    return await client.create_issue(title, body, label_list)


@router.post("/integrations/teams/message")
async def teams_send_message(text: str, title: str = "") -> dict:
    client = TeamsClient()
    return await client.send_message(text, title)


@router.post("/integrations/pipedrive/deal")
async def pipedrive_create_deal(title: str, person_id: int | None = None, value: float = 0) -> dict:
    client = PipedriveClient()
    return await client.create_deal(title, person_id, value)


@router.post("/integrations/snowflake/event")
async def snowflake_insert_event(
    session_id: str,
    channel: str,
    sentiment: str = "",
    summary: str = "",
) -> dict:
    client = SnowflakeClient()
    return await client.insert_conversation_event(session_id, channel, sentiment, summary)


@router.post("/integrations/pagerduty/incident")
async def pagerduty_create_incident(title: str, body: str = "", urgency: str = "high") -> dict:
    return await PagerDutyClient().create_incident(title, body, urgency)


@router.post("/integrations/linear/issue")
async def linear_create_issue(title: str, description: str = "") -> dict:
    return await LinearClient().create_issue(title, description)


@router.post("/integrations/bigquery/event")
async def bigquery_insert_event(
    session_id: str, channel: str, sentiment: str = "", summary: str = ""
) -> dict:
    return await BigQueryClient().insert_conversation_event(session_id, channel, sentiment, summary)


@router.post("/integrations/help-scout/conversation")
async def help_scout_create_conversation(subject: str, body: str, customer_email: str) -> dict:
    return await HelpScoutClient().create_conversation(subject, body, customer_email)


@router.post("/integrations/clickup/task")
async def clickup_create_task(name: str, description: str = "", list_id: str = "") -> dict:
    return await ClickUpClient().create_task(name, description, list_id)


@router.post("/integrations/trello/card")
async def trello_create_card(name: str, desc: str = "", list_id: str = "") -> dict:
    return await TrelloClient().create_card(name, desc, list_id)


@router.post("/integrations/front/message")
async def front_create_message(subject: str, body: str, to: str) -> dict:
    return await FrontClient().create_message(subject, body, to)


@router.post("/integrations/amplitude/event")
async def amplitude_track_event(event_type: str, session_id: str = "", channel: str = "") -> dict:
    return await AmplitudeClient().track_event(event_type, session_id=session_id, properties={"channel": channel})


@router.post("/integrations/azure-devops/work-item")
async def azure_devops_create_work_item(title: str, description: str = "", work_item_type: str = "Task") -> dict:
    return await AzureDevOpsClient().create_work_item(title, description, work_item_type)


@router.get("/integrations/shopify/customer")
async def shopify_find_customer(email: str) -> dict:
    customer = await ShopifyClient().find_customer(email)
    return customer or {"found": False}


@router.get("/integrations/stripe/customer")
async def stripe_find_customer(email: str) -> dict:
    customer = await StripeClient().find_customer(email)
    return customer or {"found": False}


@router.post("/integrations/mailchimp/subscriber")
async def mailchimp_add_subscriber(email: str, first_name: str = "", last_name: str = "") -> dict:
    return await MailchimpClient().add_subscriber(email, first_name, last_name)


@router.post("/integrations/zoho/lead")
async def zoho_create_lead(last_name: str, email: str = "", company: str = "") -> dict:
    return await ZohoCRMClient().create_lead(last_name, email, company)


@router.get("/integrations/bamboohr/employee")
async def bamboohr_find_employee(email: str) -> dict:
    employee = await BambooHRClient().find_employee(email)
    return employee or {"found": False}


@router.post("/integrations/ringcentral/notify")
async def ringcentral_send_notification(text: str, title: str = "Nexus alert") -> dict:
    return await RingCentralClient().send_notification(text, title)


@router.post("/integrations/confluence/page")
async def confluence_create_page(title: str, body: str = "") -> dict:
    return await ConfluenceClient().create_page(title, body)


@router.post("/integrations/dynamics/case")
async def dynamics_create_case(title: str, description: str = "") -> dict:
    return await Dynamics365Client().create_case(title, description)


@router.post("/integrations/copper/lead")
async def copper_create_lead(name: str, email: str = "") -> dict:
    return await CopperClient().create_lead(name, email)


@router.post("/integrations/marketo/lead")
async def marketo_create_lead(email: str, first_name: str = "", last_name: str = "") -> dict:
    return await MarketoClient().create_lead(email, first_name, last_name)


@router.post("/integrations/klaviyo/event")
async def klaviyo_track_event(event_name: str, email: str) -> dict:
    return await KlaviyoClient().track_event(event_name, email)


@router.post("/integrations/guru/card")
async def guru_create_card(title: str, content: str = "") -> dict:
    return await GuruClient().create_card(title, content)


@router.post("/integrations/document360/article")
async def document360_create_article(title: str, content: str = "") -> dict:
    return await Document360Client().create_article(title, content)


@router.post("/integrations/five9/disposition")
async def five9_notify_disposition(call_id: str, disposition: str, notes: str = "") -> dict:
    return await Five9Client().notify_disposition(call_id, disposition, notes)


@router.post("/integrations/genesys/callback")
async def genesys_create_callback(phone: str, name: str = "") -> dict:
    return await GenesysClient().create_callback(phone, name)


@router.post("/integrations/nice/contact")
async def nice_create_contact(phone: str, skill_id: str = "") -> dict:
    return await NiceClient().create_contact(phone, skill_id)


@router.post("/integrations/zoom/notify")
async def zoom_send_notification(text: str) -> dict:
    return await ZoomClient().send_notification(text)


@router.post("/integrations/vonage/sms")
async def vonage_send_sms(to: str, text: str) -> dict:
    return await VonageClient().send_sms(to, text)


@router.post("/integrations/dialpad/sms")
async def dialpad_send_sms(to: str, text: str) -> dict:
    return await DialpadClient().send_sms(to, text)


@router.post("/integrations/aircall/contact")
async def aircall_create_contact(first_name: str, phone: str, email: str = "") -> dict:
    return await AircallClient().create_contact(first_name, phone, email)


@router.get("/integrations/workday/worker")
async def workday_find_worker(email: str) -> dict:
    worker = await WorkdayClient().find_worker(email)
    return worker or {"found": False}


@router.get("/integrations/adp/worker")
async def adp_find_worker(email: str) -> dict:
    worker = await ADPClient().find_worker(email)
    return worker or {"found": False}


@router.post("/integrations/tableau/event")
async def tableau_publish_event(datasource_id: str, event_json: str = "{}") -> dict:
    import json
    return await TableauClient().publish_hyper_event(datasource_id, json.loads(event_json or "{}"))


@router.post("/integrations/powerbi/row")
async def powerbi_push_row(table_name: str, session_id: str, channel: str = "") -> dict:
    return await PowerBIClient().push_row(table_name, {"session_id": session_id, "channel": channel})


@router.post("/integrations/creatio/lead")
async def creatio_create_lead(name: str, email: str = "") -> dict:
    return await CreatioClient().create_lead(name, email)


@router.post("/integrations/salesloft/person")
async def salesloft_create_person(email: str, first_name: str = "", last_name: str = "") -> dict:
    return await SalesloftClient().create_person(email, first_name, last_name)


@router.post("/integrations/sharepoint/item")
async def sharepoint_add_item(title: str) -> dict:
    return await SharePointClient().add_list_item(title)


@router.post("/integrations/talkdesk/contact")
async def talkdesk_create_contact(name: str, phone: str, email: str = "") -> dict:
    return await TalkdeskClient().create_contact(name, phone, email)


@router.post("/integrations/ujet/callback")
async def ujet_schedule_callback(phone: str, reason: str = "") -> dict:
    return await UjetClient().schedule_callback(phone, reason)


@router.post("/integrations/8x8/notify")
async def eight_by_eight_notify(text: str, title: str = "Nexus") -> dict:
    return await EightByEightClient().send_notification(text, title)


@router.get("/integrations/gusto/employee")
async def gusto_find_employee(email: str) -> dict:
    employee = await GustoClient().find_employee(email)
    return employee or {"found": False}


@router.get("/integrations/epic/patient")
async def epic_patient_summary(patient_id: str) -> dict:
    return await EpicClient().get_patient_summary(patient_id)
