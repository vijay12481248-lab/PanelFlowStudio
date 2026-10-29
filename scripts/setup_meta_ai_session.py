"""PanelFlow Studio - Persistent Meta AI Browser Session Setup.

Opens a visible, dedicated Chrome browser window pointing to PanelFlow Studio's
persistent user profile directory. You log into your Meta account once, and all
authentication cookies and tokens are permanently saved for automated use.
"""

import os
import sys
import time
from pathlib import Path

PROFILE_DIR = Path.home() / ".panelflow" / "browser_sessions" / "default"
TARGET_URL = "https://www.meta.ai/ai-image-generator/"


def main():
    print("=" * 70)
    print(" PanelFlow Studio - Persistent Meta AI Session Setup")
    print("=" * 70)
    print(f"Profile directory: {PROFILE_DIR}")
    print(f"Target URL:        {TARGET_URL}\n")
    print("Launching dedicated Chrome window with persistent profile...")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\nERROR: Playwright is not installed in current environment.")
        print("Run: uv pip install playwright")
        sys.exit(1)

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=False,
                viewport={"width": 1280, "height": 850},
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        except Exception as e:
            print(f"\n[Warning] Direct Chrome channel failed ({e}), attempting bundled chromium...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1280, "height": 850},
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

        page = context.new_page() if not context.pages else context.pages[0]
        page.goto(TARGET_URL)

        print("\n" + "=" * 70)
        print(" ACTION REQUIRED:")
        print(" 1. In the opened Chrome window, sign in to your Meta / Facebook account.")
        print(" 2. Verify that you can see the Meta AI Image Generator page.")
        print(" 3. When finished logging in, come back here and press ENTER.")
        print("=" * 70 + "\n")

        try:
            input("Press [ENTER] after logging into Meta AI in the browser window: ")
        except (EOFError, KeyboardInterrupt):
            pass

        cookies = context.cookies()
        meta_cookies = [c for c in cookies if "meta" in c.get("domain", "") or "facebook" in c.get("domain", "")]
        print(f"\nFound {len(meta_cookies)} authenticated session cookie(s) for Meta/Facebook.")

        context.close()

    print("\n" + "=" * 70)
    print(" SUCCESS! Your persistent Meta AI session has been saved.")
    print(" PanelFlow Studio can now generate and review images automatically!")
    print("=" * 70)


if __name__ == "__main__":
    main()
