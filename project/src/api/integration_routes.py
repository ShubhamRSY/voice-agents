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
from src.api.deps import (
    CredentialsUpdateRequest, WebhookRegisterRequest,
    integration_router, require_settings_token, env_credentials,
)

logger = get_logger()
router = APIRouter()


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
