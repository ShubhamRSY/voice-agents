"""Nexus AI Ops — narrated product demo.

Two-pass: TTS first (know durations), then record video with perfect pause
lengths.  No overlapping narration, no per-segment video processing.

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

# ── Scene definitions (narration + visual config) ────────────────────

SCENES = [
    {
        "title": "The Problem Nexus Solves",
        "narration": (
            "Customer support teams juggle live chat, AI copilot tools, and phone systems "
            "as separate silos. Agents waste time switching contexts and customer history "
            "gets lost. Nexus AI Ops unifies all three channels into one AI-powered "
            "command centre."
        ),
        "overlay_title": "The Problem Nexus Solves",
        "overlay_body": "Fragmented customer communication across chat, copilot, and voice. Unifies everything into one console.",
        "cursor_moves": [(200, 200, 50), (1200, 600, 50)],
        "highlight": None,
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "What is Nexus?",
        "narration": (
            "It is an open-source, omnichannel AI agent platform connecting to OpenAI, "
            "Anthropic, and Gemini. It integrates with Twilio for calls and WhatsApp, "
            "and with Salesforce, Zendesk, and ServiceNow. Every interaction is recorded, "
            "responses stream in real time, and credentials are encrypted."
        ),
        "overlay_title": "What is Nexus?",
        "overlay_body": "Open-source omnichannel AI ops. Chat, copilot, voice. Any LLM, Twilio, CRM. Real-time, encrypted.",
        "cursor_moves": [],
        "highlight": None,
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "Live Health Monitoring",
        "narration": (
            "This status pill shows operators that the server and services are live. "
            "It displays connection health and whether STT and TTS engines are active. "
            "If anything goes down, the team knows instantly."
        ),
        "overlay_title": "Live Health Monitoring",
        "overlay_body": "Real-time server + STT/TTS status. No separate dashboards needed.",
        "cursor_moves": [],
        "highlight": ".status-pill",
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "Adaptive Theme Engine",
        "narration": (
            "Switch between dark, light, and system modes. Agents working long shifts "
            "benefit from dark mode in low light, while light mode works better in "
            "bright offices. Preference is saved automatically."
        ),
        "overlay_title": "Adaptive Theme",
        "overlay_body": "Dark, light, or system. Reduces eye strain. Saved preference.",
        "cursor_moves": [],
        "highlight": "#themeToggle",
        "click": ("#themeToggle", 2, "#themeToggle", 2),
        "post_wait": 0,
    },
    {
        "title": "Multi-Channel Modes",
        "narration": (
            "Chat for direct AI conversations. Copilot for pasting transcripts and "
            "getting AI-suggested replies. Voice for Twilio phone calls with live "
            "transcription. All three in one interface."
        ),
        "overlay_title": "Multi-Channel Modes",
        "overlay_body": "Chat, Copilot, Voice. One interface. No tab switching.",
        "cursor_moves": [],
        "highlight": "#headerModes",
        "click": ("#headerModes .tab[data-mode=copilot]", 1.5, "#headerModes .tab[data-mode=voice]", 1.5),
        "post_wait": 1,
    },
    {
        "title": "Sidebar & Agent Selector",
        "narration": (
            "The sidebar gives operators sessions, agent selection, mode settings, and "
            "the integrations vault. The agent selector lets them pick between general "
            "support, technical, or WhatsApp-optimised AI agents, each with its own "
            "tools and personality."
        ),
        "overlay_title": "Sidebar & Agent Selector",
        "overlay_body": "Sessions, agents, settings, vault \u2014 all in one panel.",
        "cursor_moves": [],
        "highlight": ".sidebar",
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "Session Management",
        "narration": (
            "Every conversation is a persistent session. Operators can start new ones, "
            "view history, and clear logs. All messages include timestamps, AI responses, "
            "and tool calls for full audit trail and compliance."
        ),
        "overlay_title": "Session Management",
        "overlay_body": "Persistent history. Full audit trail. Compliance-ready.",
        "cursor_moves": [],
        "highlight": ".session-rail",
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "Integrations Vault",
        "narration": (
            "The vault stores every API key: OpenAI, Anthropic, Gemini, Twilio, "
            "Salesforce, Zendesk, ServiceNow, and Slack. Credentials are encrypted "
            "at rest and never logged. No hardcoded keys."
        ),
        "overlay_title": "Integrations Vault",
        "overlay_body": "Encrypted credentials for every provider. No hardcoded keys.",
        "cursor_moves": [],
        "highlight": "#integrationsPanel",
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "Adaptive Layout",
        "narration": (
            "Dismiss the sidebar for full chat focus. The close button or hamburger "
            "menu toggles it. A reopen button appears on the left edge when collapsed. "
            "No auto-close \u2014 the operator controls visibility."
        ),
        "overlay_title": "Adaptive Layout",
        "overlay_body": "Full chat or full sidebar. You control when it is visible.",
        "cursor_moves": [],
        "highlight": "#sidebarCloseBtn",
        "click": (None, 2, None, 0),  # close sidebar via JS
        "post_wait": 0,
    },
    {
        "title": "Clean Composer & Streaming",
        "narration": (
            "Type a message and send. The AI processes it through the configured LLM "
            "and streams the response token by token via server-sent events. "
            "Supports OpenAI, Claude, and Gemini so you are never locked into one vendor."
        ),
        "overlay_title": "Clean Composer",
        "overlay_body": "Distraction-free input. Streams AI response in real time.",
        "cursor_moves": [],
        "highlight": "#input",
        "click": None,
        "post_wait": 0,
    },
    {
        "title": "Nexus AI Ops",
        "narration": (
            "An open-source, omnichannel AI command centre unifying chat, copilot, and "
            "voice. Real-time streaming, full audit trails, encrypted credentials. "
            "Thank you for watching."
        ),
        "overlay_title": "Nexus AI Ops",
        "overlay_body": "Omnichannel AI Ops. Open source. Chat, copilot, voice unified.",
        "cursor_moves": [],
        "highlight": None,
        "click": None,
        "post_wait": 0,
    },
]


# ── Browser chrome ──────────────────────────────────────────────────

CHROME = """
<style>
#nc-cursor{position:fixed;z-index:100000;pointer-events:none;width:32px;height:32px;margin:-16px 0 0 -16px;filter:drop-shadow(0 0 8px rgba(56,189,248,0.8))}
#nc-cursor svg{display:block;width:32px;height:32px}
#nc-overlay{position:fixed;bottom:40px;left:50%;transform:translateX(-50%);z-index:99999;pointer-events:none;max-width:780px;width:94%;opacity:0;transition:opacity 0.5s ease}
#nc-overlay.show{opacity:1}
#nc-overlay .nc-box{background:rgba(0,0,0,0.85);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:22px 32px;box-shadow:0 20px 60px rgba(0,0,0,0.7);text-align:center}
#nc-overlay .nc-title{color:#38bdf8;font:700 14px/1 'DM Sans',system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.14em;margin-bottom:8px}
#nc-overlay .nc-body{color:#f4f4f5;font:500 18px/1.6 'DM Sans',system-ui,sans-serif;max-width:680px;margin:0 auto}
#nc-highlight{position:fixed;z-index:99998;pointer-events:none;border:2.5px solid #38bdf8;border-radius:10px;box-shadow:0 0 0 5px rgba(56,189,248,0.15),0 0 50px rgba(56,189,248,0.15);opacity:0;transition:opacity 0.4s ease}
#nc-highlight.show{opacity:1}
</style>
"""

CURSOR_SVG = '<svg viewBox="0 0 32 32" fill="none"><path d="M4 4L12 28L16 18L26 14L4 4Z" fill="white" stroke="rgba(56,189,248,0.9)" stroke-width="1.5" stroke-linejoin="round"/><circle cx="12" cy="12" r="4" fill="rgba(56,189,248,0.3)"/></svg>'

cur = [720, 450]


def ol(title, body):
    t, b = json.dumps(title), json.dumps(body)
    return f"""
    (()=>{{let o=document.getElementById('nc-overlay');
    if(!o){{o=document.createElement('div');o.id='nc-overlay';o.innerHTML='<div class=nc-box><div class=nc-title></div><div class=nc-body></div></div>';document.body.appendChild(o);}}
    o.querySelector('.nc-title').textContent={t};o.querySelector('.nc-body').textContent={b};o.classList.add('show');}})();
    """

def hl(sel):
    s = json.dumps(sel)
    return f"""
    (()=>{{let el=document.querySelector({s}),h=document.getElementById('nc-highlight');
    if(!h){{h=document.createElement('div');h.id='nc-highlight';document.body.appendChild(h);}}
    if(el){{let r=el.getBoundingClientRect();Object.assign(h.style,{{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'}});h.classList.add('show');}}}})();
    """

def clr():
    return "document.getElementById('nc-highlight')?.classList.remove('show');"

async def mc(page, x, y, steps=30, delay=0.012):
    for i in range(1, steps+1):
        t = i/steps
        cx, cy = int(cur[0]+(x-cur[0])*t), int(cur[1]+(y-cur[1])*t)
        await page.evaluate(f"document.getElementById('nc-cursor').style.left='{cx}px';document.getElementById('nc-cursor').style.top='{cy}px';")
        await asyncio.sleep(delay)
    cur[0], cur[1] = x, y

async def ct(page, sel):
    box = await page.locator(sel).bounding_box()
    if box:
        await mc(page, int(box["x"]+box["width"]/2), int(box["y"]+box["height"]/2))

def ensure_server():
    try:
        urllib.request.urlopen(f"{URL}/api/v1/health", timeout=3)
        return None
    except Exception:
        print("Starting server...")
        proc = subprocess.Popen([sys.executable,"-m","uvicorn","src.main:app","--host","127.0.0.1","--port","8001"],cwd=ROOT_DIR,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                urllib.request.urlopen(f"{URL}/api/v1/health", timeout=2)
                return proc
            except Exception:
                time.sleep(1)
        raise RuntimeError("Server did not start")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="nova")
    parser.add_argument("--output", default="nexus-demo.webm")
    args = parser.parse_args()

    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="nexus-demo-")

    # ── Pass 1: Generate all TTS audio ──
    print(f"Generating TTS ({len(SCENES)} scenes)...")
    # Pre-compute: adjust the narration to use "Nexus" not "Nexus" for cleaner TTS
    api_key = __import__("src.config", fromlist=["get_settings"]).get_settings().openai_api_key
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    tts_segments = []
    async with httpx.AsyncClient(timeout=120) as client:
        for idx, sc in enumerate(SCENES):
            out = os.path.join(workdir, f"s{idx:02d}.mp3")
            r = await client.post("https://api.openai.com/v1/audio/speech",
                headers=headers, json={"model":"tts-1","voice":args.voice,
                "input":sc["narration"],"response_format":"mp3"})
            r.raise_for_status()
            with open(out, "wb") as f:
                f.write(r.content)
            dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",out]).strip())
            tts_segments.append({"path": out, "dur": dur})
            print(f"  Scene {idx+1}: {dur:.1f}s")

    # ── Pass 2: Record video with pauses matched to narration durations ──
    print("Recording video (with matched pause lengths)...")
    server_proc = ensure_server()

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=workdir,
            record_video_size={"width":1440,"height":900},
            viewport={"width":1440,"height":900},
            device_scale_factor=2,
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="networkidle")
        await page.add_style_tag(content=CHROME)
        await page.evaluate(f"document.body.insertAdjacentHTML('beforeend','<div id=nc-cursor>{CURSOR_SVG}</div>')")

        async def wait(sec): await page.wait_for_timeout(int(sec*1000))

        scene_starts = []  # wall-clock times
        t0 = time.time()

        for idx, (sc, seg) in enumerate(zip(SCENES, tts_segments)):
            narr_dur = seg["dur"]
            scene_starts.append(time.time() - t0)

            # Show overlay
            ol_js = ol(sc["overlay_title"], sc["overlay_body"])
            await page.evaluate(ol_js)

            # Cursor movements before highlight
            for (tx, ty, steps) in sc.get("cursor_moves", []):
                await mc(page, tx, ty, steps, 0.018)
                await wait(0.5)

            # Highlight element
            if sc.get("highlight"):
                await ct(page, sc["highlight"])
                await wait(0.5)
                await page.evaluate(hl(sc["highlight"]))
                await wait(1)

            # Wait for narration to play
            await wait(narr_dur)

            # Click actions (if any) during narration
            click_actions = sc.get("click")
            if click_actions:
                click1, wait1, click2, wait2 = click_actions
                await wait(wait1)
                if click1:
                    await ct(page, click1)
                    await wait(0.3)
                    await page.locator(click1).click()
                elif click1 is None:
                    # JS click for sidebar close
                    await page.evaluate('document.getElementById("sidebarCloseBtn")?.click()')
                await wait(wait2)
                if click2:
                    await ct(page, click2)
                    await wait(0.3)
                    await page.locator(click2).click()
                elif click2 is None:
                    await page.evaluate('document.getElementById("sidebarCloseBtn")?.click()')

            await page.evaluate(clr())

            # If not last scene, small gap before next
            if idx < len(SCENES) - 1:
                await wait(1)

        # Extra padding at end
        await wait(3)

        video_path = await page.video.path()
        await context.close()
        await browser.close()
        silent_path = os.path.join(workdir, "silent.webm")
        os.rename(video_path, silent_path)
        video_dur = time.time() - t0

    # ── Pass 3: Mix ──
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

    subprocess.run([
        "ffmpeg","-y",
        "-i", silent_path,
        *audio_inputs,
        "-c:v","libvpx-vp9","-b:v","0","-crf","30",
        "-c:a","libopus","-b:a","96k",
        "-filter_complex", ";".join(filter_parts),
        "-map","0:v:0","-map","[a]",
        output,
    ], check=True, capture_output=True)

    shutil.rmtree(workdir, ignore_errors=True)
    print(f"Done: {output} ({os.path.getsize(output)/1e6:.1f} MB)")

    if server_proc:
        server_proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
