import asyncio
import time
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

PROMPT = (
    "2D game character sprite sheet of a mechanic hero for a side-scrolling platformer. "
    "Clean grid of multiple animation frames isolated on a pure solid white background: "
    "idle stance, running animation frames, aiming rivet gun forward, and jumping. "
    "Everyday mechanic dad in brown canvas jacket, tool belt, denim jeans, work boots. "
    "Crisp clean 2D game sprite asset, sharp dark outlines, evenly spaced sprite sheet for game engine."
)

async def generate_and_download():
    print("=" * 70)
    print(" LIVE GENERATION ON META AI / CREATE")
    print("=" * 70)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating to https://www.meta.ai/create...")
        await page.goto("https://www.meta.ai/create", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # 1. Type prompt into contenteditable div
        box = page.locator('div[contenteditable="true"]').first
        await box.click()
        await page.wait_for_timeout(200)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        print(f"Typing prompt: {PROMPT[:60]}...")
        await page.keyboard.type(PROMPT, delay=5)
        await page.wait_for_timeout(1000)
        
        # 2. Click the send button (the blue arrow button)
        send_btn = page.locator("button[data-testid='composer-send-button'], button[aria-label='Send']").first
        print("Clicking Send (blue arrow)...")
        await send_btn.click()
        
        # 3. Wait for new creation card to appear in the gallery
        print("Waiting 20 seconds for Meta AI to generate the new card...")
        await page.wait_for_timeout(20000)
        
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_after_send.png")
        print("Saved meta_after_send.png")
        
        # 4. Find all creation cards / images in the Creations section
        cards = await page.locator("div[role='button']:has(img), a:has(img)").all()
        print(f"Found {len(cards)} creation cards on the page.")
        
        if cards:
            # Click the FIRST card (which is the most recent creation!)
            print("Clicking the newest card to open full-resolution lightbox...")
            await cards[0].click()
            await page.wait_for_timeout(3000)
            
            await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_card_opened.png")
            print("Saved meta_card_opened.png")
            
            # Find the full-res image URL in the modal
            full_urls = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('div[role="dialog"] img, div[aria-modal="true"] img, img'))
                    .map(i => i.currentSrc || i.src || '')
                    .filter(u => u.includes('t39.105495-0') || (u.includes('fbcdn.net') && (u.includes('.webp') || u.includes('.png'))));
            }""")
            
            print(f"Full-res URLs found in modal: {len(full_urls)}")
            if full_urls:
                target_url = full_urls[0]
                b64 = await page.evaluate("""async (url) => {
                    const resp = await fetch(url);
                    const blob = await resp.blob();
                    return new Promise((resolve) => {
                        const r = new FileReader();
                        r.onloadend = () => resolve(r.result);
                        r.readAsDataURL(blob);
                    });
                }""", target_url)
                
                if b64 and "base64," in b64:
                    raw_bytes = base64.b64decode(b64.split(",", 1)[1])
                    im = Image.open(io.BytesIO(raw_bytes))
                    dest = Path("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a/meta_real_new_spritesheet.png")
                    im.save(dest, "PNG")
                    print(f"SUCCESS: Saved REAL NEW spritesheet {dest.name} ({im.size[0]}x{im.size[1]}, {len(raw_bytes)} bytes)!")

        await context.close()

if __name__ == "__main__":
    asyncio.run(generate_and_download())
