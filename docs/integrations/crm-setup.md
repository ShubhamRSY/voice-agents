# CRM Integration Setup

Connect Nexus to Salesforce, Zendesk, or ServiceNow for customer lookups, ticket creation, and case management.

---

## Salesforce

### Prerequisites
- A Salesforce account with API access
- A Connected App with OAuth credentials

### Setup

1. In Salesforce, create a **Connected App** (Setup → App Manager → Create Connected App).
2. Enable **OAuth Settings** with scope `Access and manage your data (api)`.
3. Copy the **Consumer Key** and **Consumer Secret**.
4. In Nexus, open **☰ → Integrations** and enter:
   - **Salesforce Consumer Key**
   - **Salesforce Consumer Secret**
   - **Salesforce Username**
   - **Salesforce Password** (or password + security token)

### What Nexus Does with Salesforce

- Looks up contacts by email or phone during a conversation
- Creates support cases from chat/voice interactions
- Updates case status on resolution

### Source

[`src/integrations/crm.py`](https://github.com/ShubhamRSY/voice-agents/blob/main/src/integrations/crm.py)

---

## Zendesk

### Prerequisites
- A Zendesk account with admin access
- An API token

### Setup

1. In Zendesk, go to **Admin → Apps and integrations → Zendesk API**.
2. Generate an **API token**.
3. In Nexus, open **☰ → Integrations** and enter:
   - **Zendesk Subdomain** (e.g. `yourcompany`)
   - **Zendesk Email** (admin email)
   - **Zendesk API Token**

### What Nexus Does with Zendesk

- Searches tickets by requester email
- Creates new tickets from escalated conversations
- Adds comments to existing tickets

---

## ServiceNow

### Prerequisites
- A ServiceNow instance with REST API access
- A service account with `incident` and `user` table access

### Setup

1. In ServiceNow, create a service account under **User Administration**.
2. Assign roles: `incident_manager`, `incident_handler`, `user_admin`.
3. In Nexus, open **☰ → Integrations** and enter:
   - **ServiceNow Instance URL** (e.g. `https://yourinstance.service-now.com`)
   - **ServiceNow Username**
   - **ServiceNow Password**

### What Nexus Does with ServiceNow

- Looks up users by email
- Creates incidents from customer issues
- Updates incident state on resolution

---

## Common Settings

All CRM credentials are encrypted at rest using AES-256-GCM in the Integrations Vault. They can also be set via environment variables:

```bash
SALESFORCE_CONSUMER_KEY=...
SALESFORCE_CONSUMER_SECRET=...
SALESFORCE_USERNAME=...
SALESFORCE_PASSWORD=...
ZENDESK_SUBDOMAIN=...
ZENDESK_EMAIL=...
ZENDESK_API_TOKEN=...
SERVICENOW_INSTANCE_URL=...
SERVICENOW_USERNAME=...
SERVICENOW_PASSWORD=...
```

---

## Mock Mode

If no CRM credentials are configured, Nexus uses a mock CRM adapter that returns simulated data. All features work without a real CRM — useful for development and demos.
