import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def inspect_sidebar():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Search for text
        elem = page.get_by_text("2D video game character")
        count = await elem.count()
        print("get_by_text count:", count)
        if count > 0:
            print("Clicking element...")
            await elem.first.click()
            await page.wait_for_timeout(4000)
            print("After click URL:", page.url)
            await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_after_click_chat.png")
            print("Saved meta_after_click_chat.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(inspect_sidebar())
