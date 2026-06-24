# Zapier Setup (Catch Hook) — Nexus Agent Events

This platform can push events into Zapier using a standard webhook.

## 1) Create the Zap trigger

- App: **Webhooks by Zapier**
- Event: **Catch Hook**
- Zapier will give you a URL like `https://hooks.zapier.com/hooks/catch/XXXX/YYYY`

## 2) Register the hook with the platform

Register for a specific event type:

```bash
curl -X POST http://localhost:8000/api/v1/integrations/webhooks \
  -H "Content-Type: application/json" \
  -d '{"event_type":"conversation.started","url":"https://hooks.zapier.com/hooks/catch/XXXX/YYYY"}'
```

### Supported event types

| Event | Description |
|-------|-------------|
| `conversation.started` | New chat session started |
| `conversation.ended` | Session closed with outcome and metrics |
| `ticket.created` | Support ticket created in CRM |
| `conversation.escalated` | Human transfer / escalation requested |
| `feedback.suggestion` | Continuous improvement suggestion generated |
| `feedback.auto_adjust` | Agent parameters auto-adjusted by feedback loop |
| `connect.contact_ended` | Amazon Connect call completed |

### Amazon Connect events

If using the Amazon Connect telephony adapter, you can also register for connect-specific webhooks:

```bash
curl -X POST http://localhost:8000/api/v1/integrations/webhooks \
  -H "Content-Type: application/json" \
  -d '{"event_type":"connect.contact_ended","url":"https://hooks.zapier.com/hooks/catch/XXXX/YYYY"}'
```

## 3) Test the Zap

Trigger a chat request:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"I need help resetting my password","session_id":"zapier-demo"}'
```

Zapier should receive a payload shaped like:

```json
{
  "event": "conversation.started",
  "data": {
    "session_id": "zapier-demo",
    "channel": "chat",
    "agent_id": "chat_support"
  }
}
```

### Feedback suggestion payload

When the feedback loop generates a suggestion:

```json
{
  "event": "feedback.suggestion",
  "data": {
    "agent_id": "voice_support",
    "category": "containment",
    "title": "Containment rate 15% below target",
    "metric_before": 0.6,
    "metric_after": 0.75
  }
}
```

## 4) Map fields in Zapier actions

Examples:

- **Create a HubSpot ticket** → map `data.session_id`, `data.agent_id`
- **Post to Slack** → include `event` and `data.channel`
- **Create a Notion page** → store the event and metadata for an audit trail
- **Update Amazon Connect attributes** → use `data` payload to set contact flow attributes

## 5) Webhook security

If you configured `WEBHOOK_SIGNING_SECRET`, every webhook payload includes an
`X-Webhook-Signature` header (HMAC-SHA256). You can verify the signature in
Zapier using Code by Zapier:

```javascript
const crypto = require('crypto');
const sig = crypto
  .createHmac('sha256', process.env.YOUR_SIGNING_SECRET)
  .update(JSON.stringify(inputData.body))
  .digest('hex');
// Compare sig with inputData.headers['X-Webhook-Signature']
```
