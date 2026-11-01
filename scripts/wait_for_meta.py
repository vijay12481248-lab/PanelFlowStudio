import asyncio
import time
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

TARGET_URL = "https://www.meta.ai/prompt/2594e052-dce5-476f-9348-0c23376b294a"

async def wait_for_meta():
    print(f"Monitoring chat: {TARGET_URL}")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(TARGET_URL, timeout=45000)
        
        for i in range(20):
            await page.wait_for_timeout(3000)
            
            # Check text of the response
            text = await page.evaluate("""() => {
                const el = document.querySelector('div[data-testid*="message"], div.standard-markdown, div[role="main"]');
                return el ? el.innerText : '';
            }""")
            
            # Check for images
            imgs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('img'))
                    .map(i => i.currentSrc || i.src || '')
                    .filter(u => u.includes('fbcdn.net') && (u.includes('.webp') || u.includes('.png') || u.includes('.jpeg') || u.includes('.jpg')));
            }""")
            
            # Check if spinner is gone
            spinner_count = await page.locator("svg.animate-spin, div[role='progressbar'], [aria-label*='Loading']").count()
            
            print(f"[{i*3}s] Spinner count: {spinner_count}, Images: {len(imgs)}")
            if len(imgs) > 1:
                print("Images arrived!")
                break
                
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_live_wait.png")
        print("Saved meta_live_wait.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(wait_for_meta())
