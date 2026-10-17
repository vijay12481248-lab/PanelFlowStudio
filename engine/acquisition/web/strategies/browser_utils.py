"""
Playwright browser launching utilities with graceful system channel fallback.
Ensures Chromium instances can run even if ms-playwright default package has mismatching shell,
falling back to system Google Chrome or Microsoft Edge channels.
"""
from typing import Any


async def launch_chromium_browser(playwright_instance: Any, headless: bool = True):
    """
    Launches Chromium with fallback across system browser channels:
    1. Default Chromium (if installed in ms-playwright)
    2. 'chrome' system channel
    3. 'msedge' system channel
    """
    try:
        return await playwright_instance.chromium.launch(headless=headless)
    except Exception as default_err:
        for channel in ["chrome", "msedge"]:
            try:
                return await playwright_instance.chromium.launch(headless=headless, channel=channel)
            except Exception:
                pass
        raise default_err
