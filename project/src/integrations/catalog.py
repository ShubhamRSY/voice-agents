"""Integration catalog — honest mapping of native, webhook, and roadmap connectors."""

from __future__ import annotations

from typing import Any, Literal

IntegrationTier = Literal["native", "webhook", "roadmap"]
IntegrationCategory = Literal[
    "crm",
    "marketing",
    "knowledge",
    "ccaas",
    "telephony",
    "communication",
    "project",
    "hris",
    "bi",
    "ticketing",
    "other",
]

CATEGORY_LABELS: dict[str, str] = {
    "crm": "CRM",
    "marketing": "Marketing automation",
    "knowledge": "Knowledge management",
    "ccaas": "CCaaS",
    "telephony": "Telephony / chat",
    "communication": "Communication",
    "project": "Project management",
    "hris": "HRIS",
    "bi": "Business intelligence",
    "ticketing": "Ticketing system",
    "other": "Other",
}

TIER_LABELS: dict[str, str] = {
    "native": "Native connector",
    "webhook": "Via webhook / iPaaS",
    "roadmap": "On roadmap",
}

# provider_key maps to GET /integrations/status providers when present.
INTEGRATION_CATALOG: list[dict[str, Any]] = [
    # ── Native connectors (built in Nexus) ──────────────────────────────
    {"id": "hubspot", "name": "HubSpot", "category": "crm", "tier": "native", "provider_key": "hubspot"},
    {"id": "salesforce", "name": "Salesforce", "category": "crm", "tier": "native", "provider_key": "salesforce"},
    {"id": "zendesk", "name": "Zendesk", "category": "ticketing", "tier": "native", "provider_key": "zendesk"},
    {"id": "freshdesk", "name": "Freshworks Freshdesk", "category": "ticketing", "tier": "native", "provider_key": "freshdesk"},
    {"id": "servicenow", "name": "ServiceNow", "category": "ticketing", "tier": "native"},
    {"id": "intercom", "name": "Intercom", "category": "communication", "tier": "native", "provider_key": "intercom"},
    {"id": "slack", "name": "Slack", "category": "communication", "tier": "native"},
    {"id": "jira", "name": "Atlassian Jira", "category": "project", "tier": "native", "provider_key": "jira"},
    {"id": "asana", "name": "Asana", "category": "project", "tier": "native", "provider_key": "asana"},
    {"id": "monday", "name": "Monday.com", "category": "project", "tier": "native", "provider_key": "monday"},
    {"id": "github", "name": "GitHub", "category": "project", "tier": "native", "provider_key": "github"},
    {"id": "notion", "name": "Notion", "category": "knowledge", "tier": "native", "provider_key": "notion"},
    {"id": "twilio", "name": "Twilio", "category": "telephony", "tier": "native", "provider_key": "twilio"},
    {"id": "whatsapp", "name": "WhatsApp", "category": "telephony", "tier": "native", "provider_key": "whatsapp"},
    {"id": "amazon-connect", "name": "Amazon Connect", "category": "ccaas", "tier": "native"},
    {"id": "meta", "name": "Meta Messenger / Instagram", "category": "communication", "tier": "native", "provider_key": "meta"},
    {"id": "n8n", "name": "n8n", "category": "other", "tier": "native", "provider_key": "ipaas"},
    {"id": "zapier", "name": "Zapier", "category": "other", "tier": "native", "provider_key": "ipaas"},
    {"id": "pipedrive", "name": "Pipedrive", "category": "crm", "tier": "native", "provider_key": "pipedrive"},
    {"id": "microsoft-teams", "name": "Microsoft Teams", "category": "communication", "tier": "native", "provider_key": "teams"},
    {"id": "snowflake", "name": "Snowflake", "category": "bi", "tier": "native", "provider_key": "snowflake"},
    {"id": "pagerduty", "name": "PagerDuty", "category": "other", "tier": "native", "provider_key": "pagerduty"},
    {"id": "linear", "name": "Linear", "category": "project", "tier": "native", "provider_key": "linear"},
    {"id": "bigquery", "name": "Google BigQuery", "category": "bi", "tier": "native", "provider_key": "bigquery"},
    {"id": "help-scout", "name": "Help Scout", "category": "ticketing", "tier": "native", "provider_key": "help_scout"},
    {"id": "clickup", "name": "ClickUp", "category": "project", "tier": "native", "provider_key": "clickup"},
    {"id": "trello", "name": "Atlassian Trello", "category": "project", "tier": "native", "provider_key": "trello"},
    {"id": "front", "name": "Front", "category": "ticketing", "tier": "native", "provider_key": "front"},
    {"id": "amplitude", "name": "Amplitude", "category": "bi", "tier": "native", "provider_key": "amplitude"},
    {"id": "azure-devops", "name": "Microsoft Azure DevOps", "category": "project", "tier": "native", "provider_key": "azure_devops"},
    {"id": "shopify", "name": "Shopify", "category": "other", "tier": "native", "provider_key": "shopify"},
    {"id": "stripe", "name": "Stripe", "category": "other", "tier": "native", "provider_key": "stripe"},
    {"id": "mailchimp", "name": "Mailchimp", "category": "marketing", "tier": "native", "provider_key": "mailchimp"},
    {"id": "zoho-crm", "name": "Zoho CRM", "category": "crm", "tier": "native", "provider_key": "zoho"},
    {"id": "bamboohr", "name": "BambooHR", "category": "hris", "tier": "native", "provider_key": "bamboohr"},
    {"id": "ringcentral", "name": "RingCentral", "category": "telephony", "tier": "native", "provider_key": "ringcentral"},
    {"id": "confluence", "name": "Atlassian Confluence", "category": "knowledge", "tier": "native", "provider_key": "confluence"},
  # ── Additional native connectors ─────────────────────────────────────
    {"id": "copper", "name": "Copper", "category": "crm", "tier": "native", "provider_key": "copper"},
    {"id": "marketo", "name": "Adobe Marketo Engage", "category": "marketing", "tier": "native", "provider_key": "marketo"},
    {"id": "klaviyo", "name": "Klaviyo", "category": "marketing", "tier": "native", "provider_key": "klaviyo"},
    {"id": "guru", "name": "Guru", "category": "knowledge", "tier": "native", "provider_key": "guru"},
    {"id": "document360", "name": "Document360", "category": "knowledge", "tier": "native", "provider_key": "document360"},
    {"id": "five9", "name": "Five9", "category": "ccaas", "tier": "native", "provider_key": "five9"},
    {"id": "genesys", "name": "Genesys", "category": "ccaas", "tier": "native", "provider_key": "genesys"},
    {"id": "nice", "name": "NiCE", "category": "ccaas", "tier": "native", "provider_key": "nice"},
    {"id": "zoom", "name": "Zoom", "category": "telephony", "tier": "native", "provider_key": "zoom"},
    {"id": "vonage", "name": "Vonage", "category": "telephony", "tier": "native", "provider_key": "vonage"},
    {"id": "dialpad", "name": "Dialpad", "category": "telephony", "tier": "native", "provider_key": "dialpad"},
    {"id": "aircall", "name": "Aircall", "category": "telephony", "tier": "native", "provider_key": "aircall"},
    {"id": "workday", "name": "Workday", "category": "hris", "tier": "native", "provider_key": "workday"},
    {"id": "adp", "name": "ADP Workforce Now", "category": "hris", "tier": "native", "provider_key": "adp"},
    {"id": "tableau", "name": "Tableau", "category": "bi", "tier": "native", "provider_key": "tableau"},
    {"id": "power-bi", "name": "Microsoft Power BI", "category": "bi", "tier": "native", "provider_key": "powerbi"},
    {"id": "dynamics-365", "name": "Microsoft Dynamics 365", "category": "crm", "tier": "native", "provider_key": "dynamics"},
    {"id": "creatio", "name": "Creatio", "category": "crm", "tier": "native", "provider_key": "creatio"},
    {"id": "salesloft", "name": "Salesloft", "category": "marketing", "tier": "native", "provider_key": "salesloft"},
    {"id": "sharepoint", "name": "Microsoft SharePoint", "category": "knowledge", "tier": "native", "provider_key": "sharepoint"},
    {"id": "talkdesk", "name": "Talkdesk", "category": "ccaas", "tier": "native", "provider_key": "talkdesk"},
    {"id": "ujet", "name": "Ujet", "category": "ccaas", "tier": "native", "provider_key": "ujet"},
    {"id": "8x8", "name": "8x8", "category": "telephony", "tier": "native", "provider_key": "eight_by_eight"},
    {"id": "gusto", "name": "Gusto", "category": "hris", "tier": "native", "provider_key": "gusto"},
    {"id": "epic", "name": "Epic", "category": "other", "tier": "native", "provider_key": "epic"},
]


def catalog_summary() -> dict[str, Any]:
    native = sum(1 for i in INTEGRATION_CATALOG if i["tier"] == "native")
    webhook = sum(1 for i in INTEGRATION_CATALOG if i["tier"] == "webhook")
    roadmap = sum(1 for i in INTEGRATION_CATALOG if i["tier"] == "roadmap")
    return {
        "total": len(INTEGRATION_CATALOG),
        "native": native,
        "webhook": webhook,
        "roadmap": roadmap,
        "categories": list(CATEGORY_LABELS.keys()),
    }


def get_catalog(*, category: str | None = None, tier: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    items = INTEGRATION_CATALOG
    if category and category != "all":
        items = [i for i in items if i["category"] == category]
    if tier and tier != "all":
        items = [i for i in items if i["tier"] == tier]
    if q:
        needle = q.lower().strip()
        items = [i for i in items if needle in i["name"].lower() or needle in i["id"]]
    return [
        {
            **item,
            "category_label": CATEGORY_LABELS.get(item["category"], item["category"]),
            "tier_label": TIER_LABELS.get(item["tier"], item["tier"]),
        }
        for item in items
    ]
