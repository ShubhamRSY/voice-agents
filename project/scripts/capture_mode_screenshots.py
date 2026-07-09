#!/usr/bin/env python3
"""Capture full-page Nexus screenshots for Chat, Copilot, Voice, and Integrations.

Requires: pip install playwright && playwright install chromium

Usage:
  # Terminal 1 — local UI (no login wall):
  DEMO_MODE=true AUTH_REQUIRED=false uvicorn src.main:app --port 8765

  # Terminal 2:
  python scripts/capture_mode_screenshots.py --base-url http://127.0.0.1:8765

Or production (must be logged in — pass credentials):
  python scripts/capture_mode_screenshots.py \\
    --base-url https://yournexus.duckdns.org \\
    --email you@example.com --password 'your-password'
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "exports" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_MOCK_ME = {
    "user_id": "user-screenshot",
    "email": "demo@nexus.io",
    "name": "Demo User",
    "role": "admin",
    "tenant_id": "default",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://yournexus.duckdns.org")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--mock-auth", action="store_true", help="Mock /auth/me for UI screenshots")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    modes = [
        ("chat", "01-chat.png"),
        ("copilot", "02-copilot.png"),
        ("voice", "03-voice.png"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})

        if args.mock_auth:
            page.add_init_script("""
                localStorage.setItem('nexus_auth_token', 'screenshot-demo-token');
                localStorage.setItem('nexus_auth_user', JSON.stringify({
                  id: 'user-screenshot', email: 'demo@nexus.io', name: 'Demo User',
                  role: 'admin', tenant_id: 'default'
                }));
                localStorage.setItem('nexus_theme', 'dark');
            """)

            def _mock_me(route):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(_MOCK_ME),
                )

            page.route("**/api/v1/auth/me", _mock_me)

        page.goto(args.base_url.rstrip("/"), wait_until="networkidle", timeout=120_000)

        if not args.mock_auth and page.locator("#loginForm").is_visible(timeout=3000):
            if not args.email or not args.password:
                browser.close()
                raise SystemExit(
                    "Login required. Run locally with AUTH_REQUIRED=false or pass --email and --password."
                )
            page.fill("#loginEmail", args.email)
            page.fill("#loginPassword", args.password)
            page.click("#loginSubmit")
            page.wait_for_selector("#appShell:not(.hidden)", timeout=30_000)

        page.wait_for_selector("#headerModes", timeout=30_000)
        page.wait_for_selector("#appShell", timeout=30_000)
        # Force dark theme (default UI is dark; avoids light screenshots on macOS)
        page.evaluate("""
            () => {
              localStorage.setItem('nexus_theme', 'dark');
              document.body.dataset.theme = '';
            }
        """)
        time.sleep(2)

        for mode, filename in modes:
            page.click(f'.header-modes .tab[data-mode="{mode}"]')
            page.wait_for_function(
                f'document.body.dataset.mode === "{mode}"',
                timeout=10_000,
            )
            time.sleep(1.2)
            path = OUT_DIR / filename
            page.screenshot(path=str(path), full_page=False)
            print(f"Captured {mode} -> {path}")

        # Public integrations catalog (no auth)
        integrations_url = f"{args.base_url.rstrip('/')}/integrations"
        page.goto(integrations_url, wait_until="networkidle", timeout=120_000)
        page.wait_for_selector("#grid, #statsRow, main", timeout=30_000)
        time.sleep(1.5)
        integrations_path = OUT_DIR / "04-integrations.png"
        page.screenshot(path=str(integrations_path), full_page=True)
        print(f"Captured integrations -> {integrations_path}")

        browser.close()

    print(f"\nDone. Screenshots in {OUT_DIR}")


if __name__ == "__main__":
    main()
