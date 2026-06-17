# Zapier Setup (Catch Hook) — Agent Events

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

Supported event types (current):

- `conversation.started`
- `conversation.ended`
- `ticket.created`
- `conversation.escalated`

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

## 4) Map fields in Zapier actions

Examples:

- Create a HubSpot ticket → map `data.session_id`, `data.agent_id`
- Post to Slack → include `event` and `data.channel`
- Create a Notion page → store the event and metadata for an audit trail

