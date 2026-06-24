"""Nexus AI Ops — narrated interactive product demo.

Two-pass: TTS first (know durations), then record video with perfect pause
lengths. Cursor hovers over each UI component with explanation overlays.

Usage:  python scripts/demo.py [--voice nova] [--output nexus-demo.webm]
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import httpx

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
URL = "http://127.0.0.1:8001"

# ── Scene definitions ────────────────────────────────────────────────
# Each scene: narration, overlay text, a list of cursor hovers over real UI elements,
# optional highlight, optional click, optional typing simulation.

SCENES = [
    {
        "title": "Welcome to Nexus",
        "narration": (
            "Welcome to Nexus AI Ops — an open source omnichannel AI command centre "
            "that unifies chat, copilot, and voice into one console. Let us walk through "
            "every feature. Watch the cursor as we explore."
        ),
        "overlay_title": "Nexus AI Ops",
        "overlay_body": "Omnichannel AI command centre. Chat + Copilot + Voice. Open source.",
        "hovers": [
            {"label": "Main Interface", "body": "Nexus AI Ops console — all channels, one place.", "selector": "body", "hold": 2.0},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Live Health Status",
        "narration": (
            "The green status pill shows server health at a glance. It tells operators "
            "that the backend, speech-to-text, and text-to-speech engines are all running. "
            "If any service goes down, the team knows instantly."
        ),
        "overlay_title": "Health Monitoring",
        "overlay_body": "Real-time server + STT/TTS status — no separate dashboards needed.",
        "hovers": [
            {"label": "Status Pill", "body": "Live indicator: server, STT, TTS health. Green = all OK.", "selector": ".status-pill", "hold": 2.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Adaptive Theme",
        "narration": (
            "Switch between dark, light, and system theme modes with one click. "
            "Agents working night shifts can reduce eye strain with dark mode, while "
            "bright offices work better in light mode. The preference is saved automatically."
        ),
        "overlay_title": "Theme Engine",
        "overlay_body": "Dark, light, or system. Reduces eye strain. Persisted preference.",
        "hovers": [
            {"label": "Theme Toggle", "body": "Click to cycle: dark, light, system. Auto-saved.", "selector": "#themeToggle", "hold": 1.5},
        ],
        "click": ("#themeToggle", 1.0),
        "post_wait": 1.0,
    },
    {
        "title": "Multi-Channel Modes",
        "narration": (
            "Three conversation modes in one interface. Chat for direct AI conversations. "
            "Copilot for pasting transcripts and getting AI-suggested replies. Voice for "
            "Twilio phone calls with live transcription. No tab switching needed."
        ),
        "overlay_title": "Channel Modes",
        "overlay_body": "Chat, Copilot, Voice — three modes, one console. No tab switching.",
        "hovers": [
            {"label": "Chat Tab", "body": "Direct AI conversation. Streams responses token by token.", "selector": ".tab[data-mode='chat']", "hold": 1.5},
            {"label": "Copilot Tab", "body": "Paste transcripts, get AI-suggested replies instantly.", "selector": ".tab[data-mode='copilot']", "hold": 1.5},
            {"label": "Voice Tab", "body": "Twilio phone calls with live transcription & AI responses.", "selector": ".tab[data-mode='voice']", "hold": 1.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Sidebar Navigation",
        "narration": (
            "The sidebar keeps everything organised. Sessions let you review past conversations. "
            "The agent selector picks the right AI persona for each channel. Settings configure "
            "model parameters. And the integrations vault stores all encrypted API keys."
        ),
        "overlay_title": "Sidebar Panel",
        "overlay_body": "Sessions, agent selector, settings, encrypted integrations vault.",
        "hovers": [
            {"label": "Session Rail", "body": "Persistent conversation history. Full audit trail.", "selector": ".session-rail", "hold": 1.5},
            {"label": "Agent Selector", "body": "Pick persona: General, Technical, WhatsApp-optimised.", "selector": "#agentSelect", "hold": 1.5},
            {"label": "Integrations Vault", "body": "Encrypted keys: OpenAI, Anthropic, Gemini, Twilio, CRMs.", "selector": "#integrationsPanel", "hold": 1.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Chat Composer & Streaming",
        "narration": (
            "Let us send a real message. The composer is clean and distraction-free. "
            "We type our question, press send, and the AI streams the response back "
            "token by token through server-sent events. You see the answer form in real time."
        ),
        "overlay_title": "Chat Composer",
        "overlay_body": "Distraction-free input. Real-time SSE streaming from any LLM.",
        "hovers": [
            {"label": "Message Input", "body": "Type any question here. Supports multi-line.", "selector": "#input", "hold": 1.5},
            {"label": "Send Button", "body": "Sends message to the configured LLM (OpenAI, Claude, Gemini).", "selector": "#sendBtn", "hold": 1.0},
        ],
        "click": None,
        "typing": {"selector": "#input", "text": "What can you help me with?", "hold_before": 1.0, "hold_after": 1.5},
        "post_wait": 4.0,
    },
    {
        "title": "Adaptive Layout",
        "narration": (
            "Dismiss the sidebar when you need full focus on the conversation. "
            "The close button hides it, and a reopen button appears on the left edge. "
            "Operators control visibility — it never auto-closes."
        ),
        "overlay_title": "Adaptive Layout",
        "overlay_body": "Dismiss sidebar for full chat focus. No auto-close. Operator controls visibility.",
        "hovers": [
            {"label": "Sidebar Close", "body": "Click to collapse sidebar. Reopen button appears on left edge.", "selector": "#sidebarCloseBtn", "hold": 1.5},
        ],
        "click": ("#sidebarCloseBtn", 1.0),
        "post_wait": 2.0,
    },
    {
        "title": "Voice Mode & Calling",
        "narration": (
            "Switch to Voice mode to make and receive Twilio phone calls. "
            "The voice panel shows caller ID, call duration, and live transcription. "
            "The AI agent speaks back through Twilio's media streams with natural voice synthesis."
        ),
        "overlay_title": "Voice Calling",
        "overlay_body": "Twilio inbound/outbound calls. Live transcription. AI voice responses via TTS.",
        "hovers": [
            {"label": "Voice Mode Tab", "body": "Switch to Twilio voice calls with live transcription.", "selector": ".tab[data-mode='voice']", "hold": 1.5},
            {"label": "Call Controls", "body": "Dial, answer, hang up. Caller ID and duration displayed.", "selector": "#voiceControls", "hold": 1.5},
            {"label": "Live Transcription", "body": "Real-time STT transcription of the call.", "selector": "#transcriptPanel", "hold": 1.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Copilot Mode",
        "narration": (
            "Copilot mode lets agents paste long transcripts from existing support tickets. "
            "Nexus analyses the conversation and suggests a reply. The agent reviews and edits "
            "before sending — keeping the human in the loop while saving minutes per ticket."
        ),
        "overlay_title": "Copilot Mode",
        "overlay_body": "Paste transcripts, get AI-suggested replies. Human-in-the-loop. Saves minutes per ticket.",
        "hovers": [
            {"label": "Copilot Tab", "body": "Paste support transcripts. AI analyses and suggests replies.", "selector": ".tab[data-mode='copilot']", "hold": 1.5},
            {"label": "Copilot Input", "body": "Paste transcript here. AI generates draft response.", "selector": "#copilotInput", "hold": 1.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Integrations & CRMs",
        "narration": (
            "Nexus connects to every major CRM and helpdesk — Salesforce, Zendesk, "
            "ServiceNow — plus Slack for team notifications. The integrations vault "
            "encrypts all credentials at rest. Nothing is hardcoded or logged in plain text."
        ),
        "overlay_title": "CRM Integrations",
        "overlay_body": "Salesforce, Zendesk, ServiceNow, Slack. Encrypted credentials. No hardcoded keys.",
        "hovers": [
            {"label": "Integrations Vault", "body": "One-click auth. Encrypted at rest. No plain text secrets.", "selector": "#integrationsPanel", "hold": 2.0},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Outbound Calling",
        "narration": (
            "Operators can make outbound calls directly from the console. "
            "Enter a phone number, and Nexus places the call through Twilio. "
            "The AI agent can handle the first interaction or the operator can take over. "
            "Call logs, recordings, and transcripts are saved automatically."
        ),
        "overlay_title": "Outbound Dialler",
        "overlay_body": "Dial from console. AI handles first interaction. Auto-logged calls.",
        "hovers": [
            {"label": "Dial Pad", "body": "Enter number and call. Twilio handles the PSTN connection.", "selector": "#dialPad", "hold": 1.5},
            {"label": "Call Logs", "body": "Every call recorded. Transcripts, duration, outcomes saved.", "selector": "#callLogPanel", "hold": 1.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Feedback & Optimisation",
        "narration": (
            "Post-call and post-chat surveys feed into Nexus's feedback engine. "
            "CSAT scores trigger automatic adjustments to agent personality, response "
            "length, and escalation thresholds. The system gets smarter over time "
            "without manual tuning."
        ),
        "overlay_title": "Feedback Engine",
        "overlay_body": "CSAT-driven auto-adjustment. Personality, tone, thresholds. Self-optimising.",
        "hovers": [
            {"label": "CSAT Survey", "body": "Post-interaction ratings. Drives automatic behaviour tuning.", "selector": "#feedbackPanel", "hold": 1.5},
            {"label": "Performance Trends", "body": "Track CSAT, resolution rate, handle time over days/weeks.", "selector": "#trendsPanel", "hold": 1.5},
        ],
        "click": None,
        "post_wait": 0.5,
    },
    {
        "title": "Nexus AI Ops — Summary",
        "narration": (
            "Nexus AI Ops is an open-source, omnichannel AI command centre unifying "
            "chat, copilot, and voice. Real-time streaming. Encrypted credentials. "
            "CRM integrations. Call recording. Feedback-driven optimisation. "
            "Thank you for watching."
        ),
        "overlay_title": "Nexus AI Ops",
        "overlay_body": "Omnichannel AI Ops. Open source. Chat, copilot, voice unified.",
        "hovers": [
            {"label": "Thank You", "body": "nexus-ai-ops.com | github.com/ShubhamRSY/voice-agents", "selector": "body", "hold": 3.0},
        ],
        "click": None,
        "post_wait": 0,
    },
]


# ── Browser chrome (cursor + overlay) ────────────────────────────────

CHROME = """
<style>
#nc-cursor{position:fixed;z-index:100000;pointer-events:none;width:32px;height:32px;margin:-16px 0 0 -16px;filter:drop-shadow(0 0 12px rgba(56,189,248,0.9));transition:none}
#nc-cursor svg{display:block;width:32px;height:32px}
#nc-tooltip{position:fixed;z-index:99999;pointer-events:none;max-width:320px;opacity:0;transition:opacity 0.25s ease;transform:translate(-50%,-56px)}
#nc-tooltip.show{opacity:1}
#nc-tooltip .nc-tip{background:rgba(15,23,42,0.92);backdrop-filter:blur(16px);border:1px solid rgba(56,189,248,0.25);border-radius:12px;padding:10px 16px;box-shadow:0 8px 32px rgba(0,0,0,0.5);text-align:center}
#nc-tooltip .nc-tip-label{color:#38bdf8;font:600 12px/1.2 'DM Sans',system-ui,sans-serif;letter-spacing:0.08em;margin-bottom:3px}
#nc-tooltip .nc-tip-body{color:#e4e4e7;font:400 13px/1.5 'DM Sans',system-ui,sans-serif}
#nc-overlay{position:fixed;bottom:40px;left:50%;transform:translateX(-50%);z-index:99998;pointer-events:none;max-width:800px;width:94%;opacity:0;transition:opacity 0.5s ease}
#nc-overlay.show{opacity:1}
#nc-overlay .nc-box{background:rgba(0,0,0,0.85);backdrop-filter:blur(24px);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:24px 36px;box-shadow:0 24px 80px rgba(0,0,0,0.7);text-align:center}
#nc-overlay .nc-title{color:#38bdf8;font:700 15px/1 'DM Sans',system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.14em;margin-bottom:8px}
#nc-overlay .nc-body{color:#f4f4f5;font:500 19px/1.6 'DM Sans',system-ui,sans-serif;max-width:700px;margin:0 auto}
#nc-highlight{position:fixed;z-index:99997;pointer-events:none;border:2.5px solid #38bdf8;border-radius:10px;box-shadow:0 0 0 5px rgba(56,189,248,0.15),0 0 60px rgba(56,189,248,0.15);opacity:0;transition:opacity 0.35s ease}
#nc-highlight.show{opacity:1}
</style>
"""

CURSOR_SVG = '<svg viewBox="0 0 32 32" fill="none"><path d="M4 4L12 28L16 18L26 14L4 4Z" fill="white" stroke="rgba(56,189,248,0.9)" stroke-width="1.5" stroke-linejoin="round"/><circle cx="12" cy="12" r="5" fill="rgba(56,189,248,0.35)"/></svg>'

# ── JS helpers injected into the page ─────────────────────────────────

def ol_js(title, body):
    t, b = json.dumps(title), json.dumps(body)
    return f"""
    (()=>{{let o=document.getElementById('nc-overlay');
    if(!o){{o=document.createElement('div');o.id='nc-overlay';o.innerHTML='<div class=nc-box><div class=nc-title></div><div class=nc-body></div></div>';document.body.appendChild(o);}}
    o.querySelector('.nc-title').textContent={t};o.querySelector('.nc-body').textContent={b};o.classList.add('show');}})();
    """

def tt_js(label, body, x, y):
    label_str, body_str = json.dumps(label), json.dumps(body)
    return f"""
    (()=>{{let t=document.getElementById('nc-tooltip');
    if(!t){{t=document.createElement('div');t.id='nc-tooltip';t.innerHTML='<div class=nc-tip><div class=nc-tip-label></div><div class=nc-tip-body></div></div>';document.body.appendChild(t);}}
    t.querySelector('.nc-tip-label').textContent={label_str};t.querySelector('.nc-tip-body').textContent={body_str};
    t.style.left='{x}px';t.style.top='{y}px';t.classList.add('show');}})();
    """

def hl_js(sel):
    s = json.dumps(sel)
    return f"""
    (()=>{{let el=document.querySelector({s}),h=document.getElementById('nc-highlight');
    if(!h){{h=document.createElement('div');h.id='nc-highlight';document.body.appendChild(h);}}
    if(el){{let r=el.getBoundingClientRect();Object.assign(h.style,{{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'}});h.classList.add('show');}}}})();
    """

def clr_js():
    return ("document.getElementById('nc-highlight')?.classList.remove('show');"
            "document.getElementById('nc-tooltip')?.classList.remove('show');")


# ── Cursor movement ──────────────────────────────────────────────────

cursor_pos = [720, 450]

async def move_cursor(page, x, y, steps=30, delay=0.012):
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(cursor_pos[0] + (x - cursor_pos[0]) * t)
        cy = int(cursor_pos[1] + (y - cursor_pos[1]) * t)
        await page.evaluate(
            f"document.getElementById('nc-cursor').style.left='{cx}px';"
            f"document.getElementById('nc-cursor').style.top='{cy}px';"
        )
        await asyncio.sleep(delay)
    cursor_pos[0], cursor_pos[1] = x, y


async def move_to_selector(page, selector):
    """Move cursor to the centre of a DOM element."""
    box = await page.locator(selector).bounding_box()
    if box:
        cx = int(box["x"] + box["width"] / 2)
        cy = int(box["y"] + box["height"] / 2)
        await move_cursor(page, cx, cy)
        return cx, cy
    return None


# ── Server management ────────────────────────────────────────────────

def ensure_server():
    try:
        urllib.request.urlopen(f"{URL}/api/v1/health", timeout=3)
        return None
    except Exception:
        print("Starting server...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8001"],
            cwd=ROOT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            try:
                urllib.request.urlopen(f"{URL}/api/v1/health", timeout=2)
                return proc
            except Exception:
                time.sleep(1)
        raise RuntimeError("Server did not start")


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="nova")
    parser.add_argument("--output", default="nexus-demo.webm")
    parser.add_argument("--headless", action="store_true", default=True)
    args = parser.parse_args()

    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="nexus-demo-")

    # ── Pass 1: Generate all TTS audio ──
    print(f"Generating TTS ({len(SCENES)} scenes)...")
    api_key = __import__("src.config", fromlist=["get_settings"]).get_settings().openai_api_key
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    tts_segments = []
    async with httpx.AsyncClient(timeout=120) as client:
        for idx, sc in enumerate(SCENES):
            out = os.path.join(workdir, f"s{idx:02d}.mp3")
            r = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers=headers,
                json={"model": "tts-1", "voice": args.voice, "input": sc["narration"], "response_format": "mp3"},
            )
            r.raise_for_status()
            with open(out, "wb") as f:
                f.write(r.content)
            dur = float(
                subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]
                ).strip()
            )
            tts_segments.append({"path": out, "dur": dur})
            print(f"  Scene {idx+1}: {dur:.1f}s")

    # ── Pass 2: Record video with cursor interactions ──
    print("Recording video...")
    server_proc = ensure_server()

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            record_video_dir=workdir,
            record_video_size={"width": 1440, "height": 900},
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="networkidle")
        await page.add_style_tag(content=CHROME)
        await page.evaluate(
            f"document.body.insertAdjacentHTML('beforeend','<div id=nc-cursor>{CURSOR_SVG}</div>')"
        )

        async def wait(sec):
            await page.wait_for_timeout(int(sec * 1000))

        scene_starts = []
        t0 = time.time()

        for idx, (sc, seg) in enumerate(zip(SCENES, tts_segments)):
            narr_dur = seg["dur"]
            scene_starts.append(time.time() - t0)

            # Show scene overlay
            await page.evaluate(ol_js(sc["overlay_title"], sc["overlay_body"]))
            await wait(0.3)

            # Process hovers: move cursor, show tooltip, highlight, wait
            hovers = sc.get("hovers", [])

            for hi, hv in enumerate(hovers):
                sel = hv["selector"]
                label = hv["label"]
                body = hv["body"]
                hold = hv.get("hold", 1.5)

                # Move cursor to element
                pos = await move_to_selector(page, sel)
                if pos:
                    cx, cy = pos
                    # Show tooltip above cursor
                    await page.evaluate(tt_js(label, body, cx, cy))
                    # Highlight element
                    if sel != "body":
                        await page.evaluate(hl_js(sel))
                    else:
                        await page.evaluate(clr_js())

                await wait(hold)

                # Clear highlight between hovers
                if hi < len(hovers) - 1:
                    await page.evaluate(clr_js())
                    await wait(0.2)

            # Clear tooltip + highlight after all hovers
            await page.evaluate(clr_js())

            # Typing simulation (if any)
            typing = sc.get("typing")
            if typing:
                sel = typing["selector"]
                text = typing["text"]
                hold_before = typing.get("hold_before", 1.0)
                hold_after = typing.get("hold_after", 2.0)
                await wait(hold_before)
                # Click the input
                await move_to_selector(page, sel)
                await wait(0.3)
                await page.locator(sel).click()
                await page.locator(sel).fill("")
                await wait(0.2)
                # Type character by character
                for ch in text:
                    await page.locator(sel).type(ch, delay=60)
                    await asyncio.sleep(0.01)
                await wait(0.5)
                # Click send
                send_sel = "#sendBtn"
                await move_to_selector(page, send_sel)
                await wait(0.3)
                await page.locator(send_sel).click()
                await wait(hold_after)

            # Click action
            click = sc.get("click")
            if click:
                sel, delay_before = click
                await move_to_selector(page, sel)
                await wait(delay_before)
                await page.locator(sel).click()
                await page.evaluate(clr_js())

            # If we still have narration time left, wait
            elapsed_so_far = time.time() - t0 - scene_starts[-1]
            remaining = narr_dur - elapsed_so_far
            if remaining > 0:
                await wait(remaining)

            # Gap before next scene
            if idx < len(SCENES) - 1:
                await page.evaluate(clr_js())
                await wait(sc.get("post_wait", 0.5))

        await wait(3)
        video_path = await page.video.path()
        await context.close()
        await browser.close()
        silent_path = os.path.join(workdir, "silent.webm")
        os.rename(video_path, silent_path)
        video_dur = time.time() - t0

    # ── Pass 3: Mix audio with video ──
    print(f"Mixing {video_dur:.1f}s video with audio...")
    filter_parts = []
    for i, (sc, seg, st) in enumerate(zip(SCENES, tts_segments, scene_starts)):
        delay_ms = int(st * 1000)
        filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[s{i}]")
    mix_in = "".join(f"[s{i}]" for i in range(len(SCENES)))
    filter_parts.append(f"{mix_in}amix=inputs={len(SCENES)}:duration=longest:dropout_transition=0[a]")

    audio_inputs = []
    for seg in tts_segments:
        audio_inputs += ["-i", seg["path"]]

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", silent_path,
            *audio_inputs,
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30",
            "-c:a", "libopus", "-b:a", "96k",
            "-filter_complex", ";".join(filter_parts),
            "-map", "0:v:0", "-map", "[a]",
            output,
        ],
        check=True, capture_output=True,
    )

    shutil.rmtree(workdir, ignore_errors=True)
    print(f"Done: {output} ({os.path.getsize(output)/1e6:.1f} MB)")

    if server_proc:
        server_proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
