import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def check():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/create", timeout=30000)
        await page.wait_for_timeout(3000)
        
        imgs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img')).map(i => ({
                src: i.currentSrc || i.src || '',
                w: i.naturalWidth,
                h: i.naturalHeight,
                rectW: Math.round(i.getBoundingClientRect().width),
                rectH: Math.round(i.getBoundingClientRect().height)
            })).filter(x => x.w > 200 || x.rectW > 200);
        }""")
        print(f"Images with width > 200: {len(imgs)}")
        for idx, im in enumerate(imgs[:10]):
            print(f"[{idx}] natural: {im['w']}x{im['h']}, rect: {im['rectW']}x{im['rectH']}")
            print("    src:", im['src'][:100])
        await context.close()

if __name__ == "__main__":
    asyncio.run(check())
