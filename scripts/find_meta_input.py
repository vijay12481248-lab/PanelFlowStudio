import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def find_input():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/create", timeout=30000)
        await page.wait_for_timeout(2000)
        
        locators = ['textarea', '[contenteditable="true"]', 'input[type="text"]', '[role="textbox"]']
        for loc in locators:
            elems = await page.locator(loc).all()
            print(f'Selector "{loc}": found {len(elems)}')
            for i, e in enumerate(elems):
                placeholder = await e.get_attribute("placeholder") or ""
                aria = await e.get_attribute("aria-label") or ""
                visible = await e.is_visible()
                tag = await e.evaluate("el => el.tagName")
                print(f'  [{i}] tag={tag}, visible={visible}, placeholder="{placeholder}", aria="{aria}"')
        await context.close()

if __name__ == "__main__":
    asyncio.run(find_input())
