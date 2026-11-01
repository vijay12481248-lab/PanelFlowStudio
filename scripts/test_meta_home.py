import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def open_card():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        print("Meta AI home title:", await page.title())
        print("URL:", page.url)
        
        # Check if chat input exists on https://www.meta.ai/
        box = page.locator('div[contenteditable="true"], textarea').first
        if await box.is_visible():
            print("Chat input found on https://www.meta.ai/!")
            placeholder = await box.get_attribute("placeholder") or await box.inner_text()
            print("Placeholder/Text:", placeholder)
        
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_home.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(open_card())
