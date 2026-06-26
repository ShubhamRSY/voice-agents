"""Integration vault, webhooks, and enterprise platform connectors."""

from typing import Any

from fastapi import APIRouter, Request, HTTPException
from structlog import get_logger

from src.config import get_settings, reload_settings
from src.integrations.secrets_vault import CREDENTIAL_KEYS, WEBHOOK_EVENTS, get_secrets_vault
from src.integrations.slack import SlackNotifier
from src.integrations.zendesk import ZendeskClient
from src.integrations.servicenow import ServiceNowClient
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
    creds = vault.credential_status(env_credentials())
    hooks = vault.webhook_status()

    return {
        "encryption": {
            "enabled": vault.path.exists(),
            "vault_path": str(vault.path),
            "key_source": "env" if settings.integrations_encryption_key else "local_file",
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
async def save_credentials(request: Request, body: CredentialsUpdateRequest) -> dict[str, Any]:
    require_settings_token(request)
    vault = get_secrets_vault()
    updates = body.model_dump(exclude_unset=True)
    vault.set_credentials(updates)
    reload_settings()
    integration_router.load_from_vault()
    return {
        "status": "saved",
        "updated": list(updates.keys()),
        "providers": (await integrations_status())["providers"],
    }


@router.delete("/integrations/credentials/{credential_key}")
async def delete_credential(request: Request, credential_key: str) -> dict[str, str]:
    require_settings_token(request)
    if credential_key not in CREDENTIAL_KEYS:
        raise HTTPException(status_code=400, detail=f"Unsupported credential: {credential_key}")
    get_secrets_vault().clear_credential(credential_key)
    reload_settings()
    integration_router.load_from_vault()
    return {"status": "cleared", "credential": credential_key}


@router.post("/integrations/webhooks")
async def register_webhook(request: Request, body: WebhookRegisterRequest) -> dict[str, str]:
    require_settings_token(request)
    if body.event_type not in WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {body.event_type}")
    integration_router.register_webhook(body.event_type, body.url)
    return {"status": "registered", "event_type": body.event_type}


@router.delete("/integrations/webhooks/{event_type}")
async def delete_webhook(request: Request, event_type: str) -> dict[str, str]:
    require_settings_token(request)
    if event_type not in WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {event_type}")
    integration_router.unregister_webhook(event_type)
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
