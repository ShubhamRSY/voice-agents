# Twilio Integration Setup

Connect Nexus to Twilio for PSTN phone calls and WhatsApp messaging.

---

## Prerequisites

- A [Twilio account](https://www.twilio.com) (free trial works)
- A Twilio phone number with voice capabilities
- Nexus running on a publicly accessible URL (use [ngrok](https://ngrok.com) for development)

---

## Step 1: Get Your Twilio Credentials

1. Log in to the [Twilio Console](https://console.twilio.com).
2. Copy your **Account SID** and **Auth Token** from the dashboard.
3. Buy or select a phone number under **Phone Numbers > Manage > Buy a Number**.

---

## Step 2: Configure Nexus

### Via the UI

1. Open the Nexus console → **☰** menu → **Integrations**.
2. Fill in:
   - **Twilio Account SID**
   - **Twilio Auth Token**
   - **Twilio Phone Number** (e.g. `+12061234567`)
   - **Webhook Base URL** (your public ngrok/production URL)
3. Click **Save Encrypted**.

### Via Environment Variables

Add to `config/environment/.env`:

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+12061234567
TWILIO_WEBHOOK_BASE_URL=https://your-tunnel.ngrok.io
```

---

## Step 3: Set Up ngrok (Development)

```bash
ngrok http 8001
```

Copy the HTTPS forwarding URL (e.g. `https://abc123.ngrok.io`).

---

## Step 4: Configure Twilio Webhook

1. In the Twilio Console, go to **Phone Numbers > Manage > Active Numbers**.
2. Click your phone number.
3. Under **Voice**, set:
   - **When a call comes in:** `Webhook`
   - **URL:** `https://your-tunnel.ngrok.io/api/v1/voice/twilio`
   - **HTTP method:** `POST`
4. Click **Save**.

---

## Step 5: Test It

Call your Twilio number. You should hear the Nexus AI greeting. Speak a question and the AI will respond.

For WhatsApp:
- Configure the WhatsApp Sandbox in Twilio Console
- Set the webhook to `POST https://your-tunnel.ngrok.io/api/v1/voice/twilio`

---

## Troubleshooting

| Issue | Likely Cause | Fix |
|-------|-------------|-----|
| No greeting on call | Webhook URL not set or unreachable | Check ngrok tunnel, verify URL in Twilio Console |
| "Service unavailable" response | Twilio credentials invalid | Re-check Account SID and Auth Token |
| Audio cuts off | Timeout or TTS error | Check `OPENAI_API_KEY` is set for TTS |
| WhatsApp not responding | Sandbox not configured | Set up WhatsApp Sandbox in Twilio Console |

---

## Source

- [`src/telephony/twilio_handler.py`](https://github.com/ShubhamRSY/voice-agents/blob/main/src/telephony/twilio_handler.py)
- [`src/telephony/call_router.py`](https://github.com/ShubhamRSY/voice-agents/blob/main/src/telephony/call_router.py)
