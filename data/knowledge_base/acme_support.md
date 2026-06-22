# Acme Support Knowledge Base

## Billing & Payments

Q: How do I update my payment method?
A: To update your payment method, log into your Acme account and navigate to Settings > Billing > Payment Methods. You can add a new credit card, set a default payment method, or remove expired cards. Changes take effect immediately for future billing cycles. Enterprise accounts can also set up ACH transfers by contacting their account manager.

Q: When is my billing date?
A: Acme bills on a monthly cycle starting from your sign-up date. You can view your next billing date and invoice history in Settings > Billing. Annual plans are billed once per year on your anniversary date. Invoices are typically generated within 24 hours of the billing date and emailed to the account owner.

Q: How do I request a refund?
A: Refunds are available within 30 days of purchase for annual plans and within 7 days for monthly plans. To request a refund, contact our support team with your account email and reason for cancellation. Refunds are processed within 5-7 business days and credited back to the original payment method. Partial refunds are available for annual plans used for less than 6 months.

Q: What happens if a payment fails?
A: If a payment fails, we'll send you an email notification and retry the payment up to 3 times over 5 days. Your account will remain active during this grace period. After 5 days without successful payment, access to paid features will be limited. To restore full access, update your payment method in Settings > Billing and contact support to clear any outstanding balance.

## Account Management

Q: How do I reset my password?
A: To reset your password, go to the login page and click 'Forgot Password'. Enter your registered email address and check your inbox for a reset link. The link expires after 1 hour. Follow the link to create a new password that must be at least 8 characters long and include a number and a special character. If you don't receive the email, check your spam folder or contact support for assistance.

Q: How do I add team members?
A: Account owners and admins can invite team members from Settings > Team. Click 'Invite Member', enter their email address, and select a role: Admin (full access), Member (standard access), or Viewer (read-only). The invitee will receive an email with a link to join. You can manage roles, remove members, or resend invitations from the same page. Your plan determines the maximum number of team members.

Q: How do I export my data?
A: You can export your data from Settings > Data Export. Choose your preferred format: CSV (spreadsheets), JSON (developers), or PDF (reports). Select the data types to include: conversations, tickets, analytics, or all data. Exports are prepared asynchronously — you'll receive a download link via email when ready. Large exports may take up to 24 hours. Data is retained for 90 days after account cancellation.

Q: What happens when I upgrade or downgrade my plan?
A: Upgrading takes effect immediately and you'll be charged a prorated amount for the remainder of the billing cycle. Downgrading takes effect at the end of your current billing cycle. When downgrading, ensure your usage is within the new plan limits. Enterprise plan changes require contacting your account manager. You can view and compare plans in Settings > Subscription.

## Technical Support

Q: Which browsers are supported?
A: Acme Platform supports the latest two major versions of Chrome, Firefox, Safari, and Edge. For the best experience, enable JavaScript and cookies in your browser settings. We recommend keeping your browser updated to the latest version. Internet Explorer is not supported. Mobile browsers are supported on iOS Safari and Android Chrome with a responsive interface designed for touch interaction.

Q: What are the API rate limits?
A: The Acme API allows 1,000 requests per minute for enterprise plans and 100 requests per minute for standard plans. Rate limits are applied per API key. Exceeded requests receive a 429 Too Many Requests response. Implement exponential backoff with jitter for retries. You can monitor your current usage and limits from the Developer Dashboard. Contact support to request a rate limit increase for your plan.

Q: How do I authenticate API requests?
A: Include your API key in the X-API-Key header for all API requests. You can generate and manage API keys from the Developer Dashboard. API keys inherit the permissions of the user who created them. Rotate keys regularly and never expose them in client-side code. For OAuth 2.0 support, enterprise customers can configure SSO integration. Invalid or expired keys will receive a 401 Unauthorized response.

Q: What is the API base URL?
A: The production API base URL is https://api.acme.com/v1. For development and testing, use https://api-staging.acme.com/v1. All endpoints return JSON responses. The OpenAPI specification is available at /docs when running the platform locally. Webhook events are delivered to your configured endpoint URL with HMAC-SHA256 signatures for verification.

## Troubleshooting

Q: Why am I getting a 403 Forbidden error?
A: A 403 Forbidden error means your request lacks proper authorization. Check that your API key is valid, active, and included in the X-API-Key header. Verify that your API key has the required permissions for the requested resource. If using SSO, ensure your session hasn't expired — try logging out and back in. Contact your account admin if you believe you should have access.

Q: Why is the platform running slowly?
A: Platform performance can be affected by browser cache, network connectivity, and concurrent usage. Try clearing your browser cache and cookies. Check your internet connection speed. Reduce the number of concurrent API requests. Close unused browser tabs. If the issue persists, check our status page at status.acme.com for any ongoing incidents. Enterprise customers can request a performance audit.

Q: How do I report a bug?
A: To report a bug, contact support with a detailed description including: steps to reproduce, expected vs actual behavior, browser/device info, and any error messages or screenshots. Critical bugs (system down, data loss) are prioritized for same-day response. You can also check known issues in our Developer Community or submit directly via the in-app feedback tool in Settings > Help.

Q: How do I contact Acme Support?
A: Acme Support is available 24/7 via chat, email, and phone. Chat: click the chat icon in the bottom-right corner of the platform. Email: support@acme.com (responses within 4 hours). Phone: +1-800-ACME-HELP (available 6 AM - 6 PM PST). Enterprise customers have a dedicated account manager and priority phone line with 15-minute response SLA. Average chat response time is under 2 minutes.

## Integrations & Developer

Q: How do I set up a webhook?
A: Configure webhooks from Settings > Developer > Webhooks. Enter your endpoint URL and select the events you want to receive. We'll send a verification ping to confirm the endpoint is reachable. Webhook payloads are signed with HMAC-SHA256 using your webhook signing secret. Verify signatures on your end before processing. Retry logic: failed deliveries are retried up to 5 times with exponential backoff.

Q: Does Acme support SSO?
A: Yes, Acme supports SAML 2.0 and OIDC-based SSO for enterprise plans. Supported providers include Okta, Azure AD, Google Workspace, and OneLogin. Set up SSO from Settings > Security > Single Sign-On. You'll need your provider's metadata URL or XML. SSO is enforced at the organization level — once configured, all team members must log in via SSO. Contact support for assistance with custom SSO configurations.

Q: What iPaaS integrations are available?
A: Acme integrates with n8n and Zapier for workflow automation. Pre-built templates are available for common workflows: create ticket from conversation, sync contacts to CRM, send Slack notifications for escalations, and more. Browse the integrations catalog from Settings > Integrations. Custom webhook events can be consumed in any automation platform that supports JSON webhooks.

## Product & Features

Q: What AI models does Acme use?
A: Acme uses GPT-4o-mini by default for chat and voice agents, with support for Claude and Gemini as alternative providers. The AI orchestrator uses LangGraph for ReAct agent loops. Responses are grounded in your knowledge base to reduce hallucination risk. Voice agents use OpenAI Whisper for STT and OpenAI TTS (warm female voice) for speech synthesis. All AI features work offline in mock mode for development.

Q: Can I use my own LLM API key?
A: Yes, you can configure your own OpenAI, Anthropic, or Gemini API keys in Settings > Integrations. Your keys are encrypted at rest using Fernet (AES) encryption and never exposed in API responses. You can switch between providers per agent in the agent configuration. Without API keys, the platform runs in mock mode with deterministic responses — all demos and tests work without any keys.

Q: How is conversation data handled?
A: Conversation data is stored in your local ChromaDB vector store and SQLite database. You can export or delete your data at any time from Settings > Data Export. We never use your conversation data for model training. API keys are encrypted at rest using Fernet symmetric encryption. Audit logs track all configuration changes. For enterprise deployments, you can configure a persistent ChromaDB volume and external database.
