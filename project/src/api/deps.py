"""Shared dependencies, models, and singletons for API route modules."""

from typing import Any

from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Request
from structlog import get_logger

from src.auth import AuthContext, get_auth_context
from src.config import get_settings, Settings
from src.api.session_manager import SessionManager
from src.integrations.secrets_vault import CREDENTIAL_KEYS
from src.integrations.webhooks import IntegrationRouter
from src.telephony.call_router import CallRouter, RoutingRule
from src.telephony.twilio_handler import TwilioVoiceHandler
from src.telephony.tts import DEFAULT_VOICE
from src.integrations.whatsapp import WhatsAppMessenger

logger = get_logger()


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="User message to the agent", examples=["What is my account balance?"])
    agent_id: str = Field("chat_support", description="Agent ID to route to", examples=["chat_support", "voice_support"])
    customer_info: str = Field("", description="Optional customer context", examples=["Customer since 2023, premium tier"])
    session_id: str = Field("", description="Existing session ID for conversation continuity", examples=["session-abc123"])


class ChatResponse(BaseModel):
    response: str = Field(description="Agent response text", examples=["Your account balance is $1,234.56."])
    agent_id: str = Field(description="Agent that handled the request")
    tool_calls: list[dict] = Field(default_factory=list, description="Tools invoked during processing")
    metrics: dict = Field(default_factory=dict, description="Response metrics (latency, mode, etc.)")
    message_id: int | None = Field(None, description="Database ID of the assistant message (for thumbs feedback)")
    session_id: str = Field("", description="Session ID for this conversation")
    locale: str = Field("en", description="Detected customer locale")


class CopilotRequest(BaseModel):
    message: str = Field(description="Agent message to get copilot assistance on", examples=["Draft a reply to this complaint"])
    conversation_summary: str = Field("", description="Prior conversation context", examples=["Customer is upset about billing error"])
    agent_id: str = Field("copilot", description="Copilot agent ID", examples=["copilot"])


class IngestRequest(BaseModel):
    source_path: str


class WebhookRegisterRequest(BaseModel):
    event_type: str
    url: str


class CredentialsUpdateRequest(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    twilio_webhook_base_url: str | None = None
    hubspot_api_key: str | None = None
    salesforce_client_id: str | None = None
    salesforce_client_secret: str | None = None
    webhook_signing_secret: str | None = None
    freshdesk_domain: str | None = None
    freshdesk_api_key: str | None = None
    intercom_access_token: str | None = None
    asana_access_token: str | None = None
    monday_api_key: str | None = None
    notion_api_key: str | None = None
    github_token: str | None = None
    github_repo: str | None = None
    teams_webhook_url: str | None = None
    pipedrive_api_token: str | None = None
    pipedrive_domain: str | None = None
    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_password: str | None = None
    snowflake_warehouse: str | None = None
    snowflake_database: str | None = None
    snowflake_schema: str | None = None
    pagerduty_api_key: str | None = None
    pagerduty_service_id: str | None = None
    linear_api_key: str | None = None
    linear_team_id: str | None = None
    bigquery_project_id: str | None = None
    bigquery_dataset_id: str | None = None
    bigquery_table_id: str | None = None
    bigquery_access_token: str | None = None
    help_scout_api_key: str | None = None
    help_scout_mailbox_id: str | None = None
    clickup_api_token: str | None = None
    clickup_list_id: str | None = None
    trello_api_key: str | None = None
    trello_api_token: str | None = None
    trello_list_id: str | None = None
    front_api_token: str | None = None
    front_channel_id: str | None = None
    amplitude_api_key: str | None = None
    azure_devops_org: str | None = None
    azure_devops_project: str | None = None
    azure_devops_pat: str | None = None
    shopify_shop_domain: str | None = None
    shopify_access_token: str | None = None
    mailchimp_api_key: str | None = None
    mailchimp_list_id: str | None = None
    mailchimp_server: str | None = None
    zoho_access_token: str | None = None
    zoho_api_domain: str | None = None
    bamboohr_subdomain: str | None = None
    bamboohr_api_key: str | None = None
    ringcentral_webhook_url: str | None = None
    confluence_base_url: str | None = None
    confluence_user_email: str | None = None
    confluence_api_token: str | None = None
    confluence_space_key: str | None = None
    dynamics_instance_url: str | None = None
    dynamics_access_token: str | None = None
    copper_api_key: str | None = None
    copper_user_email: str | None = None
    marketo_client_id: str | None = None
    marketo_client_secret: str | None = None
    marketo_base_url: str | None = None
    klaviyo_api_key: str | None = None
    guru_api_token: str | None = None
    guru_collection_id: str | None = None
    document360_api_token: str | None = None
    document360_base_url: str | None = None
    five9_webhook_url: str | None = None
    five9_api_username: str | None = None
    five9_api_password: str | None = None
    genesys_api_key: str | None = None
    genesys_region: str | None = None
    nice_api_key: str | None = None
    nice_base_url: str | None = None
    zoom_webhook_url: str | None = None
    zoom_account_id: str | None = None
    zoom_client_id: str | None = None
    zoom_client_secret: str | None = None
    vonage_api_key: str | None = None
    vonage_api_secret: str | None = None
    vonage_from_number: str | None = None
    dialpad_api_key: str | None = None
    aircall_api_id: str | None = None
    aircall_api_token: str | None = None
    workday_tenant: str | None = None
    workday_username: str | None = None
    workday_password: str | None = None
    adp_client_id: str | None = None
    adp_client_secret: str | None = None
    tableau_server_url: str | None = None
    tableau_token_name: str | None = None
    tableau_token_secret: str | None = None
    tableau_site_id: str | None = None
    powerbi_access_token: str | None = None
    powerbi_workspace_id: str | None = None
    powerbi_dataset_id: str | None = None
    creatio_base_url: str | None = None
    creatio_username: str | None = None
    creatio_password: str | None = None
    salesloft_api_key: str | None = None
    sharepoint_site_url: str | None = None
    sharepoint_access_token: str | None = None
    sharepoint_list_name: str | None = None
    talkdesk_api_token: str | None = None
    talkdesk_base_url: str | None = None
    ujet_api_key: str | None = None
    ujet_subdomain: str | None = None
    eight_by_eight_api_key: str | None = None
    eight_by_eight_webhook_url: str | None = None
    gusto_access_token: str | None = None
    gusto_company_id: str | None = None
    epic_fhir_base_url: str | None = None
    epic_fhir_access_token: str | None = None


class VoiceSimulateRequest(BaseModel):
    call_sid: str = "SIM-CALL-001"
    from_number: str = "+15551234567"
    speech: str | None = None
    sip_headers: dict[str, str] = Field(default_factory=dict)


class SpeakRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE


class LoginRequest(BaseModel):
    email: str = Field(description="User email", examples=["user@example.com"])
    password: str = Field(description="User password", examples=["SecurePass123!"])


class RegisterRequest(BaseModel):
    email: str = Field(description="User email", examples=["newuser@example.com"])
    password: str = Field(description="Password (min 8 chars)", examples=["StrongPass123!"])
    name: str = Field(description="Display name", examples=["Jane Doe"])
    tenant_name: str = Field("My Organization", description="Organization name", examples=["Acme Corp"])


class ArticleCreateRequest(BaseModel):
    title: str
    content: str
    tags: str = ""
    category: str = "general"


class ArticleUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: str | None = None
    category: str | None = None


class CSATRequest(BaseModel):
    session_id: str = Field(description="Session to rate", examples=["session-abc123"])
    score: int = Field(ge=1, le=5, description="Rating 1-5", examples=[5])
    feedback: str = Field("", description="Optional comment", examples=["Great support!"])


class WebhookEventRequest(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------

_call_router = CallRouter()
_call_router.add_rule(RoutingRule("vip", "from:+1555", "+15559999999", priority=10))
_call_router.set_fallback("+15551111111")

_sessions = SessionManager(ttl_seconds=3600, max_sessions=1000)
integration_router = IntegrationRouter()
voice_handler = TwilioVoiceHandler()
whatsapp = WhatsAppMessenger()


# ---------------------------------------------------------------------------
# Reusable dependency helpers
# ---------------------------------------------------------------------------

async def require_auth(ctx: AuthContext | None = Depends(get_auth_context)) -> AuthContext | None:
    settings = get_settings()
    if settings.auth_required:
        if ctx is None:
            raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


def get_session(session_id: str, agent_id: str, tenant_id: str = "default") -> Any:
    return _sessions.get(session_id, agent_id)


def require_settings_token(request: Request) -> None:
    settings = get_settings()
    token = settings.settings_admin_token.strip()
    if not token:
        return
    provided = request.headers.get("X-Settings-Token", "")
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Settings-Token header.")


def env_credentials() -> dict[str, str]:
    env_settings = Settings()
    return {key: getattr(env_settings, key, "") or "" for key in CREDENTIAL_KEYS}
