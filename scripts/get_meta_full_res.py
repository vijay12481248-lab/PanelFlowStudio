import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

async def get_full_res():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/create", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click on the first image card to open the full-resolution lightbox
        first_img = page.locator("div[role='button']:has(img), a:has(img)").first
        if await first_img.is_visible():
            print("Clicking first image card to open lightbox...")
            await first_img.click()
            await page.wait_for_timeout(2500)
            
            # Check for large modal image
            modal_imgs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('div[role="dialog"] img, div[aria-modal="true"] img, img'))
                    .map(i => ({
                        src: i.currentSrc || i.src || '',
                        w: i.naturalWidth,
                        h: i.naturalHeight
                    }))
                    .filter(x => x.w >= 500);
            }""")
            print("Modal images >= 500px:", modal_imgs)
            
            if modal_imgs:
                # Download full res
                import base64
                best_src = modal_imgs[0]["src"]
                b64 = await page.evaluate("""async (url) => {
                    const resp = await fetch(url);
                    const blob = await resp.blob();
                    return new Promise((resolve) => {
                        const r = new FileReader();
                        r.onloadend = () => resolve(r.result);
                        r.readAsDataURL(blob);
                    });
                }""", best_src)
                
                if b64 and "base64," in b64:
                    raw = base64.b64decode(b64.split(",", 1)[1])
                    out_path = PROJECT_ROOT / "output" / "game_sprites" / "meta_full_res_sprite.png"
                    out_path.write_bytes(raw)
                    print(f"SUCCESS: Saved full res image ({len(raw)} bytes) to {out_path}!")
            
            await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_lightbox.png")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(get_full_res())
