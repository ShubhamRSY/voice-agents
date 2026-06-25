from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

DARK = RGBColor(0x1E, 0x1E, 0x2E)
ACCENT = RGBColor(0x6C, 0x63, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xCC, 0xCC, 0xDD)
GREEN = RGBColor(0x4A, 0xDE, 0x80)
ORANGE = RGBColor(0xFF, 0xA5, 0x00)

def set_bg(slide, color=DARK):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_shape(slide, left, top, width, height, color, alpha=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape

def add_text_box(slide, left, top, width, height, text, font_size=18, color=WHITE, bold=False, alignment=PP_ALIGN.LEFT, font_name="Calibri"):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font_name
    p.alignment = alignment
    return txBox

def add_bullet_slide(slide, items, left, top, width, height, font_size=16, color=LIGHT):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = item
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.font.name = "Calibri"
        p.space_after = Pt(8)
        p.level = 0
    return txBox

def accent_line(slide, left, top, width):
    add_shape(slide, left, top, width, Pt(4), ACCENT)

# ──────────────────────────── TITLE SLIDE ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)

add_shape(slide, Inches(0), Inches(2.8), Inches(13.333), Inches(0.08), ACCENT)

add_text_box(slide, Inches(1), Inches(1.2), Inches(11), Inches(1.5),
             "NEXUS", font_size=72, color=WHITE, bold=True, alignment=PP_ALIGN.CENTER)
add_text_box(slide, Inches(1), Inches(3.2), Inches(11), Inches(1),
             "Open-Source Omnichannel AI Agent Platform", font_size=28, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text_box(slide, Inches(2), Inches(4.5), Inches(9), Inches(0.8),
             "Chat · Copilot · Voice — One Orchestrator", font_size=20, color=LIGHT, alignment=PP_ALIGN.CENTER)
add_text_box(slide, Inches(3), Inches(6.2), Inches(7), Inches(0.5),
             "github.com/ShubhamRSY/voice-agents", font_size=14, color=LIGHT, alignment=PP_ALIGN.CENTER)

# ──────────────────────────── WHAT IS NEXUS ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "What Is Nexus?", font_size=36, color=WHITE, bold=True)

add_text_box(slide, Inches(0.8), Inches(2.0), Inches(11.5), Inches(4.5),
             "Nexus is an open-source, enterprise-grade omnichannel AI agent platform that unifies customer "
             "support conversations across chat, copilot assistance, and voice telephony into a single "
             "orchestration runtime.\n\n"
             "It solves the problem of fragmented support tools by providing one AI engine that routes "
             "conversations, retrieves knowledge via RAG, supports multiple LLM providers, and improves "
             "responses through a built-in CSAT feedback loop — all from a single console.",
             font_size=18, color=LIGHT)

# ──────────────────────────── CHANNELS ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Three Channels, One Engine", font_size=36, color=WHITE, bold=True)

channels = [
    ("Chat", "Live AI conversation with SSE streaming, RAG citations,\nfragmented history, and session management."),
    ("Copilot", "Agent-assist mode — paste a customer transcript,\nget an AI-suggested reply instantly."),
    ("Voice", "PSTN telephony via Twilio, Amazon Connect, or any\nSIP/CCaaS. Live STT → AI → TTS pipeline."),
]

for i, (title, desc) in enumerate(channels):
    y = Inches(2.2 + i * 1.7)
    add_shape(slide, Inches(0.8), y, Inches(0.08), Inches(1.2), ACCENT)
    add_text_box(slide, Inches(1.2), y, Inches(3), Inches(0.5), title, font_size=24, color=ACCENT, bold=True)
    add_text_box(slide, Inches(1.2), y + Inches(0.5), Inches(10), Inches(0.8), desc, font_size=16, color=LIGHT)

# ──────────────────────────── ARCHITECTURE ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Architecture", font_size=36, color=WHITE, bold=True)

arch_items = [
    "User → REST API → Orchestrator",
    "  ├─ Session Manager (create / load / save)",
    "  ├─ RAG Engine (vector retrieval + citations)",
    "  ├─ Prompt Builder (system prompt + history + context)",
    "  ├─ LLM Provider (OpenAI, Anthropic, Gemini, Mock)",
    "  └─ SSE Streaming Response → Console",
    "",
    "Layered design: Routers → Orchestrator → Services → Providers → Infrastructure",
]
add_bullet_slide(slide, arch_items, Inches(0.8), Inches(2.0), Inches(11), Inches(4.5),
                 font_size=18, color=LIGHT)

# ──────────────────────────── MULTI-LLM ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Multi-LLM Support", font_size=36, color=WHITE, bold=True)

llms = [
    "OpenAI GPT-4o / GPT-4o-mini — default provider",
    "Anthropic Claude 3.5 — via anthropic_provider.py",
    "Google Gemini 2.0 Flash — via gemini_provider.py",
    "Mock LLM — built-in fallback (no API key needed for dev)",
    "Per-agent model configuration via YAML agent definitions",
    "Switch models without code changes — config-driven",
]
add_bullet_slide(slide, llms, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── RAG ENGINE ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "RAG Engine", font_size=36, color=WHITE, bold=True)

rag = [
    "Vector-based retrieval augmented generation",
    "Chunked knowledge base (configurable chunk size)",
    "Top-K retrieval with configurable threshold",
    "Source citations in every AI response",
    "Markdown knowledge base → vector embeddings pipeline",
    "Per-agent knowledge base configuration in YAML",
]
add_bullet_slide(slide, rag, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── VOICE TELEPHONY ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Voice Telephony", font_size=36, color=WHITE, bold=True)

voice = [
    "Twilio Programmable Voice — production-ready PSTN integration",
    "Amazon Connect — CCaaS integration",
    "Generic SIP / CCaaS — any SIP trunk",
    "VAPI.ai & Retell AI — AI voice agent overlay support",
    "Built-in simulator for local dev (no hardware required)",
    "STT: Deepgram, AssemblyAI  |  TTS: ElevenLabs, PlayHT",
    "Twilio webhook handler + status callbacks",
    "Call logs and status endpoints",
]
add_bullet_slide(slide, voice, Inches(0.8), Inches(2.0), Inches(11), Inches(4.5),
                 font_size=18, color=LIGHT)

# ──────────────────────────── FEEDBACK ENGINE ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Feedback Engine", font_size=36, color=WHITE, bold=True)

fb = [
    "Users rate responses — 👍 / 👎 / CSAT score",
    "CSAT ratings dynamically tune agent temperature",
    "Adjusts RAG retrieval threshold based on feedback",
    "Sentiment tracking across sessions",
    "All feedback logged for analysis",
    "Enables continuous improvement without manual tuning",
]
add_bullet_slide(slide, fb, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── VAULT + SECURITY ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Security & Integrations Vault", font_size=36, color=WHITE, bold=True)

sec = [
    "AES-256-GCM encrypted vault for API keys & credentials",
    "REST API for credential CRUD (keys stored encrypted at rest)",
    "JWT authentication with configurable expiry",
    "Pydantic input validation on all endpoints",
    "Strict CORS origin whitelist",
    "No secrets in .env committed to version control",
]
add_bullet_slide(slide, sec, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── CONSOLE UI ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Console UI", font_size=36, color=WHITE, bold=True)

ui = [
    "Dark mode with premium animations and micro-interactions",
    "Three-channel tabs: Chat / Copilot / Voice",
    "Per-mode message filtering with sync toggle (🔗 / ⊘)",
    "Session sidebar: create, rename, switch, clear sessions",
    "SSE streaming — word-by-word AI response display",
    "Typing indicator and streaming cursor",
    "Welcome screen with per-mode placeholders",
    "Clean, responsive layout with scrollable message history",
]
add_bullet_slide(slide, ui, Inches(0.8), Inches(2.0), Inches(11), Inches(4.5),
                 font_size=18, color=LIGHT)

# ──────────────────────────── IPAAS WEBHOOKS ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "iPaaS Webhooks", font_size=36, color=WHITE, bold=True)

wh = [
    "Lifecycle event webhooks for n8n, Zapier, and custom flows",
    "Events: session.created, message.completed, feedback.submitted",
    "Async dispatch via httpx — non-blocking",
    "Event history endpoint for debugging",
    "Connect to CRMs (Salesforce, Zendesk, ServiceNow), Slack, and more",
]
add_bullet_slide(slide, wh, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── DEPLOYMENT ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Deployment", font_size=36, color=WHITE, bold=True)

deploy = [
    "Docker: docker compose -f deploy/docker/docker-compose.yml up",
    "Bare metal: uvicorn src.main:app --host 0.0.0.0 --port 8001",
    "CI/CD: GitHub Actions — lint, test, e2e, build, deploy",
    "Configuration-driven agents via YAML (config/agents/)",
    "Environment-based settings via .env (config/environment/)",
]
add_bullet_slide(slide, deploy, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── TESTING ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
accent_line(slide, Inches(0.8), Inches(0.6), Inches(4))
add_text_box(slide, Inches(0.8), Inches(0.8), Inches(10), Inches(0.8),
             "Testing & Quality", font_size=36, color=WHITE, bold=True)

test = [
    "158+ unit tests covering all routers, services, and providers",
    "33 comprehensive E2E tests simulating real user flows",
    "Mock LLM provider enables testing without API keys",
    "Ruff linter + mypy type checking in CI",
    "Coverage reports output to reports/coverage/",
]
add_bullet_slide(slide, test, Inches(0.8), Inches(2.0), Inches(11), Inches(4),
                 font_size=18, color=LIGHT)

# ──────────────────────────── THANK YOU ────────────────────────────
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)

add_shape(slide, Inches(0), Inches(3.2), Inches(13.333), Inches(0.08), ACCENT)

add_text_box(slide, Inches(1), Inches(1.5), Inches(11), Inches(1.5),
             "Thank You", font_size=60, color=WHITE, bold=True, alignment=PP_ALIGN.CENTER)
add_text_box(slide, Inches(1), Inches(3.6), Inches(11), Inches(0.8),
             "Nexus — Open-Source Omnichannel AI Agent Platform", font_size=22, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text_box(slide, Inches(1), Inches(4.6), Inches(11), Inches(0.6),
             "MIT License  ·  github.com/ShubhamRSY/voice-agents", font_size=16, color=LIGHT, alignment=PP_ALIGN.CENTER)

# ──────────────────────────── SAVE ────────────────────────────
prs.save("Nexus_Overview.pptx")
print("Saved Nexus_Overview.pptx")
