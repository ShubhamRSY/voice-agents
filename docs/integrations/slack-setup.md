# Slack Integration Setup

Send notifications from Nexus to Slack channels for escalations, feedback suggestions, and ticket activity.

---

## Prerequisites

- A Slack workspace where you can create apps
- Permission to install apps to channels

---

## Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**.
2. Choose **From scratch**.
3. Name it (e.g. "Nexus Notifier") and select your workspace.
4. Click **Create App**.

---

## Step 2: Add Bot Token Scope

1. In the left sidebar, click **OAuth & Permissions**.
2. Under **Bot Token Scopes**, click **Add an OAuth Scope**.
3. Add: `chat:write`, `chat:write.public`, `channels:read`.
4. Click **Install to Workspace** and **Allow**.
5. Copy the **Bot User OAuth Token** (starts with `xoxb-`).

---

## Step 3: Configure Nexus

### Via the UI

1. Open the Nexus console → **☰** menu → **Integrations**.
2. Under Slack, paste your **Bot User OAuth Token**.
3. Set the **Default Channel** (e.g. `#support-escalations`).
4. Click **Save Encrypted**.

### Via Environment Variables

Add to `config/environment/.env`:

```bash
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SLACK_DEFAULT_CHANNEL=#support-escalations
```

---

## Step 4: Events That Trigger Slack Notifications

| Event | Slack Message |
|-------|---------------|
| Conversation escalated | `:rotating_light: *Escalation* — {customer} requested human agent. Session: {session_id}` |
| Feedback suggestion | `:bulb: *Improvement Suggestion* — {agent_id}: {suggestion_text}` |
| Ticket created | `:ticket: *New Ticket* — {ticket_id}: {summary}` |
| Auto-adjust applied | `:gear: *Auto-Adjust* — {agent_id}: {parameter} changed to {value}` |

---

## Troubleshooting

| Issue | Likely Cause | Fix |
|-------|-------------|-----|
| "not_in_channel" error | Bot not invited to channel | Invite bot with `/invite @Nexus Notifier` |
| Messages not sending | Wrong token or scope | Verify token starts with `xoxb-`, check scopes include `chat:write` |
| Token not saving | Encryption key missing | Set `INTEGRATIONS_ENCRYPTION_KEY` in `.env` |

---

## Source

- [`src/integrations/webhooks.py`](https://github.com/ShubhamRSY/voice-agents/blob/main/src/integrations/webhooks.py)
