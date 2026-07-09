# Nexus Cloud — Managed Hosted SaaS

Nexus Cloud runs as **shared multi-tenant hosting** on managed infrastructure (Postgres, TLS, backups). Each sign-up provisions an isolated tenant workspace — not a dedicated VM per customer.

## Live sign-up

**URL:** [/signup](https://yournexus.duckdns.org/signup)

**API:** `POST /api/v1/saas/signup`

```json
{
  "company_name": "Acme Inc",
  "admin_name": "Alex Admin",
  "email": "alex@acme.com",
  "password": "SecurePass123!",
  "plan_id": "starter"
}
```

### What gets provisioned automatically

1. New `tenant` record with slug and plan metadata  
2. Admin user (JWT returned for instant console access)  
3. `tenant_subscriptions` row (`trialing` for 14 days)  
4. Starter knowledge base (3 onboarding articles)  
5. Audit log entry `saas.workspace.provisioned`

### Without Stripe (default pilot)

Sign-up returns `status: "provisioned"` + `token` — user lands in the console immediately on a free trial.

### With Stripe (production billing)

Set in `.env`:

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
APP_PUBLIC_URL=https://yournexus.duckdns.org
```

Sign-up returns `checkout_url` → Stripe Checkout → webhook `checkout.session.completed` → workspace provisioned.

Webhook endpoint: `POST /api/v1/saas/webhooks/stripe`

## Plans

| Plan | Price | API `plan_id` |
|------|-------|---------------|
| Free | $0/mo | `free` |
| Starter | $29/mo | `starter` |
| Growth | $99/mo | `growth` |

`GET /api/v1/saas/plans` · `GET /api/v1/saas/signup/config`

## Disable public sign-up

```env
SAAS_SIGNUP_ENABLED=false
```

## Legal

Sign-up requires acceptance of:

- [/legal/terms](/legal/terms) — Terms of Service
- [/legal/privacy](/legal/privacy) — Privacy Policy

Commercial AGPL alternative: [/legal/licensing](/legal/licensing) (Startup $12k/yr, Growth $36k/yr, Enterprise from $96k/yr).

## Deploy / restart

After pulling code, restart the server so chat/RAG routes load the HF cache fix:

```bash
bash scripts/restart_local.sh   # dev
# production: systemctl restart nexus  (or redeploy Docker image)
```

Check `GET /api/v1/health` — `rag_mode` should not be broken; `vault.decrypt_ok` must be `true`.

## Architecture note

This is **honest SaaS provisioning**: one Nexus deployment, many tenants, row-level isolation via `tenant_id`. Dedicated per-customer VMs or Kubernetes namespaces are an Enterprise add-on, not required for SMB pilots.
