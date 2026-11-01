import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def inspect_submit():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/create", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Test typing into [contenteditable="true"]
        box = page.locator('div[contenteditable="true"]').first
        await box.click()
        await page.keyboard.type("2D game sprite sheet of a mechanic hero, isolated on white background")
        await page.wait_for_timeout(1000)
        
        # Inspect all visible buttons now
        buttons = await page.locator('button').all()
        for i, b in enumerate(buttons):
            if await b.is_visible():
                label = await b.get_attribute("aria-label") or ""
                text = await b.inner_text() or ""
                testid = await b.get_attribute("data-testid") or ""
                print(f"Button [{i}]: aria='{label}', text='{text}', testid='{testid}'")
                
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_typed_box.png")
        print("Screenshot of typed prompt saved.")
        await context.close()

if __name__ == "__main__":
    asyncio.run(inspect_submit())
