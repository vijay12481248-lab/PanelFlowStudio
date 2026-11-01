import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys
from PIL import Image
import io
import base64

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

TARGET_URL = "https://www.meta.ai/prompt/2594e052-dce5-476f-9348-0c23376b294a"

async def check_rendered_sprite():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        # Navigate to the latest chat
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click the top chat item in history
        chat_item = page.locator("div:has-text('2D game character sprite')").first
        if await chat_item.is_visible():
            await chat_item.click()
            await page.wait_for_timeout(4000)
            
        print("Current URL:", page.url)
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_live_rendered.png")
        print("Saved meta_live_rendered.png")
        
        # Check text in the chat
        text = await page.evaluate("() => document.body.innerText")
        lines = [l for l in text.split('\\n') if l.strip()]
        for l in lines[-10:]:
            print("Chat line:", l)
            
        # Check all images in the chat area
        imgs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('div[data-testid*="message"] img, div[role="main"] img, img'))
                .map(i => ({
                    src: i.currentSrc || i.src || '',
                    w: i.naturalWidth,
                    h: i.naturalHeight
                }))
                .filter(x => x.src.includes('fbcdn.net') && x.w > 150);
        }""")
        
        print(f"Found {len(imgs)} candidate images in message area:")
        dest_dir = Path("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a")
        for idx, it in enumerate(imgs):
            print(f"[{idx}] {it['w']}x{it['h']} -> {it['src'][:80]}")
            b64 = await page.evaluate("""async (url) => {
                const resp = await fetch(url);
                const blob = await resp.blob();
                return new Promise((resolve) => {
                    const r = new FileReader();
                    r.onloadend = () => resolve(r.result);
                    r.readAsDataURL(blob);
                });
            }""", it["src"])
            if b64 and "base64," in b64:
                raw = base64.b64decode(b64.split(",", 1)[1])
                im = Image.open(io.BytesIO(raw))
                fdest = dest_dir / f"meta_spritesheet_final_{idx+1}.png"
                im.save(fdest, "PNG")
                print(f"SAVED: {fdest.name} ({im.size[0]}x{im.size[1]})")

        await context.close()

if __name__ == "__main__":
    asyncio.run(check_rendered_sprite())
