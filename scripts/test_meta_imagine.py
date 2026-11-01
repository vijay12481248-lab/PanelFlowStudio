import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def test_create_images():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click the "Create images" pill button
        create_btn = page.get_by_text("Create images").first
        if await create_btn.is_visible():
            print("Clicking 'Create images' pill button...")
            await create_btn.click()
            await page.wait_for_timeout(2000)
            
        print("URL after clicking Create images:", page.url)
        # Type into the prompt box
        box = page.locator("div[contenteditable='true'], textarea").first
        await box.click()
        prompt_text = "Imagine a 2D game sprite sheet of a mechanic hero, isolated on pure white background, running and idle animation frames"
        print(f"Typing: {prompt_text}")
        await page.keyboard.type(prompt_text, delay=10)
        await page.wait_for_timeout(1000)
        
        # Send
        send = page.locator("button[data-testid='composer-send-button'], button[aria-label='Send']").first
        print("Clicking send...")
        await send.click()
        
        # Wait 15 seconds
        print("Waiting 15 seconds for Meta Imagine generation...")
        await page.wait_for_timeout(15000)
        
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_imagine_result.png")
        print("Saved meta_imagine_result.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(test_create_images())
