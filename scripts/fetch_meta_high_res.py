import asyncio
import base64
from playwright.async_api import async_playwright
from pathlib import Path
import sys
from PIL import Image
import io

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def fetch_true_image():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/create", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click on the latest image card to open modal
        card = page.locator("div[role='button']:has(img), a:has(img)").first
        await card.click()
        await page.wait_for_timeout(3000)
        
        # Get the webp images excluding svg
        img_urls = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img'))
                .map(i => i.currentSrc || i.src || '')
                .filter(u => u.includes('fbcdn.net') && (u.includes('.webp') || u.includes('.png') || u.includes('.jpeg') || u.includes('.jpg')));
        }""")
        
        print(f"Found {len(img_urls)} candidate FB CDN image URLs.")
        if img_urls:
            target_url = img_urls[0]
            print("Fetching:", target_url[:80])
            
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
                print(f"Downloaded image format={im.format}, size={im.size}")
                
                # Save as high-res PNG
                dest1 = PROJECT_ROOT / "output" / "game_sprites" / "meta_true_full_res_sprite.png"
                dest2 = Path("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a/meta_true_full_res_sprite.png")
                im.save(dest1, "PNG")
                im.save(dest2, "PNG")
                print(f"SUCCESS: Saved true full-res PNG ({im.size[0]}x{im.size[1]}) to {dest2}!")
        
        await context.close()

if __name__ == "__main__":
    asyncio.run(fetch_true_image())
