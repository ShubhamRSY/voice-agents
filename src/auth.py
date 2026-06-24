"""JWT authentication, multi-tenant support, and role-based access control."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import structlog
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import DATA_DIR
from src.database import db

logger = structlog.get_logger()

JWT_SECRET_FILE = DATA_DIR / ".jwt_secret"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 86400  # 24h

security = HTTPBearer(auto_error=False)


def _get_jwt_secret() -> str:
    if JWT_SECRET_FILE.exists():
        return JWT_SECRET_FILE.read_text().strip()
    secret = secrets.token_hex(32)
    JWT_SECRET_FILE.write_text(secret)
    JWT_SECRET_FILE.chmod(0o600)
    return secret


def _base64url_encode(data: bytes) -> str:
    return data.hex()


def _base64url_decode(s: str) -> bytes:
    return bytes.fromhex(s)


def _hmac_sha256(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_jwt(payload: dict) -> str:
    secret = _get_jwt_secret()
    header = _base64url_encode(b'{"alg":"HS256","typ":"JWT"}')
    body = _base64url_encode(
        __import__("json").dumps({**payload, "exp": int(time.time()) + JWT_EXPIRY_SECONDS}).encode()
    )
    sig = _hmac_sha256(secret, f"{header}.{body}")
    return f"{header}.{body}.{sig}"


def decode_jwt(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, body_b64, sig = parts
        secret = _get_jwt_secret()
        expected = _hmac_sha256(secret, f"{header_b64}.{body_b64}")
        if not hmac.compare_digest(sig, expected):
            return None
        payload = __import__("json").loads(_base64url_decode(body_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


@dataclass
class AuthContext:
    user_id: str
    tenant_id: str
    email: str
    name: str
    role: str

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_agent(self) -> bool:
        return self.role in ("admin", "agent")


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthContext | None:
    if credentials is None:
        return None
    payload = decode_jwt(credentials.credentials)
    if payload is None:
        return None
    return AuthContext(
        user_id=payload.get("sub", ""),
        tenant_id=payload.get("tenant_id", ""),
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        role=payload.get("role", "agent"),
    )


async def require_auth(ctx: AuthContext | None = Depends(get_auth_context)) -> AuthContext:
    if ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


async def require_admin(ctx: AuthContext = Depends(require_auth)) -> AuthContext:
    if not ctx.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return ctx


def verify_password(plain: str, hashed: str) -> bool:
    if len(hashed) < 16:
        return False
    salt = hashed[:16]
    return _hmac_sha256(salt, plain) == hashed[16:]


def hash_password(plain: str) -> str:
    salt = secrets.token_hex(8)
    return salt + _hmac_sha256(salt, plain)


# --- Demo users/seeds ---

DEMO_TENANT_ID = "demo-acme"
DEMO_USERS = [
    {"id": "admin-001", "email": "admin@acme.com", "password": "admin123", "name": "Sarah Admin", "role": "admin"},
    {"id": "agent-001", "email": "agent@acme.com", "password": "agent123", "name": "Mike Agent", "role": "agent"},
    {"id": "viewer-001", "email": "viewer@acme.com", "password": "viewer123", "name": "Lisa Viewer", "role": "viewer"},
]


def seed_demo_data() -> None:
    from src.database import db

    tenant = db.get_tenant(DEMO_TENANT_ID)
    if tenant:
        return

    db.create_tenant(DEMO_TENANT_ID, "Acme Corporation", "acme-corp", {
        "plan": "enterprise",
        "channels": ["chat", "voice", "copilot", "whatsapp"],
    })

    for u in DEMO_USERS:
        db.create_user(u["id"], DEMO_TENANT_ID, u["email"], hash_password(u["password"]), u["name"], u["role"])

    articles = [
        {"title": "How to reset your password", "content": "To reset your password, go to the login page and click 'Forgot Password'. Enter your registered email address and check your inbox for a reset link. Follow the link to create a new password. Your new password must be at least 8 characters long and include a number and a special character.", "tags": "password,account,security", "category": "account"},
        {"title": "Understanding your billing cycle", "content": "Acme bills on a monthly cycle starting from your sign-up date. Invoices are generated on the 1st of each month. You can view your billing history and download invoices from the Billing section in your account settings. Payments are processed via secure credit card or ACH transfer.", "tags": "billing,payment,invoice", "category": "billing"},
        {"title": "How to request a refund", "content": "Refunds are available within 30 days of purchase for annual plans and within 7 days for monthly plans. To request a refund, contact support with your account email and reason for cancellation. Refunds are processed within 5-7 business days and credited back to the original payment method.", "tags": "refund,billing,cancellation", "category": "billing"},
        {"title": "Managing team members", "content": "Account owners can invite team members from the Team page in Settings. Enter their email address and select a role (Admin, Member, or Viewer). Each plan has a team member limit. You can remove members or change roles at any time. Team members receive an invitation email to join.", "tags": "team,members,users,admin", "category": "account"},
        {"title": "API rate limits and best practices", "content": "The Acme API allows 1,000 requests per minute for enterprise plans and 100 requests per minute for standard plans. Implement exponential backoff for retries. Cache responses where possible. Include your API key in the X-API-Key header. Monitor your usage from the Developer Dashboard.", "tags": "api,developer,rate-limit", "category": "technical"},
        {"title": "Supported browsers", "content": "Acme Platform supports the latest two major versions of Chrome, Firefox, Safari, and Edge. For the best experience, enable JavaScript and cookies. Internet Explorer is not supported.", "tags": "browser,support,technical", "category": "technical"},
        {"title": "Data export options", "content": "You can export your data from Settings > Data Export. Choose between CSV, JSON, or PDF formats. Exports include conversations, tickets, and analytics. Large exports are sent via email as a download link. Data is retained for 90 days after account cancellation.", "tags": "export,data,privacy", "category": "account"},
        {"title": "Troubleshooting 403 errors", "content": "A 403 Forbidden error means your request lacks proper authorization. Check that your API key is valid and included in the request header. Verify your permissions for the requested resource. If using SSO, ensure your session hasn't expired. Contact support if the issue persists.", "tags": "error,api,403,troubleshooting", "category": "troubleshooting"},
        {"title": "Performance optimization tips", "content": "For optimal platform performance: clear your browser cache regularly, limit concurrent API requests, use our CDN-hosted SDKs, enable compression, and batch API calls where possible. Enterprise customers can request a performance audit from their account manager.", "tags": "performance,optimization,tips", "category": "technical"},
        {"title": "Contacting Acme Support", "content": "Acme Support is available 24/7 via chat, email, and phone. Chat: click the chat icon in the bottom-right corner. Email: support@acme.com. Phone: +1-800-ACME-HELP. Enterprise customers have a dedicated account manager and priority phone line. Average response time is under 2 minutes for chat and under 4 hours for email.", "tags": "support,contact,help", "category": "general"},
    ]
    for art in articles:
        db.create_article(DEMO_TENANT_ID, art["title"], art["content"], art["tags"], art["category"])

    _seed_demo_conversations()

    logger.info("demo_data_seeded", tenant=DEMO_TENANT_ID, users=len(DEMO_USERS), articles=len(articles))


def _seed_demo_conversations() -> None:
    """Pre-seed conversation history for demo tenant."""
    conversations = [
        {
            "session_id": "demo-conv-001",
            "agent_id": "chat_support",
            "customer_info": "jane@acme.com",
            "messages": [
                ("user", "Hi, I need help resetting my password."),
                ("assistant", "I can help with that! To reset your password, go to the login page and click 'Forgot Password'. Enter your registered email and check your inbox for a reset link. Would you like me to walk you through it?"),
                ("user", "Yes please, I've tried but didn't get the email."),
                ("assistant", "Let me look up your account. I found your account, Jane. Let me check what's happening. The email may have gone to your spam folder. Could you check there? Also, make sure you're using the email jane@acme.com that's registered on your account."),
                ("user", "Found it in spam! Thanks."),
                ("assistant", "Great! Click the link in the email and create a new password. It must be at least 8 characters with a number and special character. Let me know if you need any further help!"),
            ],
            "csat_score": 5,
        },
        {
            "session_id": "demo-conv-002",
            "agent_id": "chat_support",
            "customer_info": "bob@acme.com",
            "messages": [
                ("user", "I'm getting a 403 error on the API."),
                ("assistant", "A 403 Forbidden error typically means your API key lacks the required permissions. Let me look up your account details."),
                ("user", "I'm using the admin key though."),
                ("assistant", "I found your account. Let me check your API key scopes. Your key appears to be valid but may be restricted. Could you verify in the Developer Dashboard that your key has the 'full_access' scope? Also check that your account is in good standing."),
                ("user", "Ah, I see - it was set to read-only. Fixed it!"),
                ("assistant", "Perfect! Your API requests should work now. If you encounter any other issues, don't hesitate to reach out."),
            ],
            "csat_score": 4,
        },
        {
            "session_id": "demo-conv-003",
            "agent_id": "voice_support",
            "customer_info": "+15551234567",
            "messages": [
                ("user", "Hello, I need to speak to someone about my bill."),
                ("assistant", "Hello! Thanks for calling Acme Support. I'd be happy to help you with your billing concerns. Could I start by looking up your account? What's the email address associated with your account?"),
                ("user", "It's alice@acme.com."),
                ("assistant", "Thank you, Alice. I found your account. You're on our Professional plan billed at $99/month. I can see your most recent invoice was generated on the 1st. What specifically concerns you about your bill?"),
                ("user", "I was charged twice this month."),
                ("assistant", "I understand that's frustrating. Let me create a ticket for our billing team to investigate the duplicate charge. I've filed ticket TKT-2024 for you. A billing specialist will follow up within 24 hours. Is there anything else I can help with?"),
            ],
            "csat_score": 3,
        },
    ]

    for conv in conversations:
        sid = conv["session_id"]
        db.create_session(sid, DEMO_TENANT_ID, conv["agent_id"], "chat", conv["customer_info"])
        for role, content in conv["messages"]:
            db.save_message(sid, role, content)
        if conv.get("csat_score"):
            db.save_csat(sid, DEMO_TENANT_ID, conv["csat_score"], "Demo pre-seeded feedback")
        db.end_session(sid)

    logger.info("demo_conversations_seeded", count=len(conversations))
