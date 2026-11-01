import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def inspect_prev_chat():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click on "Game creation image ideas" or "Creating Ghibli walk animation"
        chat = page.get_by_text("Creating Ghibli walk animation").first
        if await chat.is_visible():
            await chat.click()
            await page.wait_for_timeout(4000)
            await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_ghibli_chat.png")
            print("Saved ghibli chat screenshot!")
            
            # Print the text in this chat
            texts = await page.locator("div[data-testid*='message'], div.standard-markdown, div[role='article']").all_inner_texts()
            for t in texts:
                print("--- MSG ---")
                print(t[:200])
                
        await context.close()

if __name__ == "__main__":
    asyncio.run(inspect_prev_chat())
