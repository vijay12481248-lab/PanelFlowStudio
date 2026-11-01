import asyncio
import base64
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge
from playwright.async_api import async_playwright

PROMPT = (
    "2D video game character sprite sheet of a mechanic hero for a side-scrolling platformer. "
    "Clean grid layout of multiple sprite animation frames isolated on a pure solid white background. "
    "Includes side-view frames: idle standing, running sequence (4 frames), aiming a rivet gun forward, and jumping. "
    "Rugged mechanic dad wearing canvas jacket, tool belt, denim jeans, and heavy boots. "
    "Clean 2D game sprite art, crisp black outlines, evenly spaced sprite sheet for game engine."
)

async def generate_sprites():
    print("=" * 70)
    print(" Generating Proper 2D Sprite Sheet via Meta AI")
    print("=" * 70)
    
    out_dir = PROJECT_ROOT / "output" / "game_sprites"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.meta.ai/create...")
        await page.goto("https://www.meta.ai/create", timeout=45000)
        await page.wait_for_timeout(3000)
        
        # Collect existing image sources
        existing_srcs = set(await page.evaluate("""
            () => Array.from(document.querySelectorAll('img')).map(i => i.currentSrc || i.src || '')
        """))
        print(f"Recorded {len(existing_srcs)} baseline image(s) on page.")
        
        # Click into input box
        input_box = page.locator('div[contenteditable="true"]').first
        await input_box.click()
        await page.wait_for_timeout(200)
        
        # Clear and type prompt
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(PROMPT, delay=5)
        await page.wait_for_timeout(500)
        
        # Click send button
        send_btn = page.locator("button[data-testid='composer-send-button'], button[aria-label='Send']").first
        print("Clicking Send button...")
        await send_btn.click()
        
        # Wait for generation (Meta AI usually takes 10-25 seconds)
        print("Waiting for Meta AI to generate images...")
        start_time = time.monotonic()
        new_images = []
        
        for attempt in range(40):
            await page.wait_for_timeout(1000)
            
            # Check for new images with significant size
            img_candidates = await page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('img');
                    const results = [];
                    for (const img of imgs) {
                        const src = img.currentSrc || img.src || '';
                        const rect = img.getBoundingClientRect();
                        const w = img.naturalWidth || rect.width;
                        const h = img.naturalHeight || rect.height;
                        if (w >= 150 && h >= 150 && src.startsWith('http')) {
                            results.push({ src: src, width: Math.round(w), height: Math.round(h) });
                        }
                    }
                    return results;
                }
            """)
            
            new_candidates = [c for c in img_candidates if c["src"] not in existing_srcs]
            if len(new_candidates) >= 1 and (time.monotonic() - start_time) > 8:
                print(f"Found {len(new_candidates)} new generated image(s)!")
                new_images = new_candidates
                break
        
        # Save screenshot of generation state
        await page.screenshot(path=str(out_dir / "meta_generation_result.png"))
        
        # Extract and download new image bytes
        downloaded = []
        for idx, item in enumerate(new_images[:4]):
            src = item["src"]
            try:
                b64 = await page.evaluate("""
                    async (url) => {
                        const resp = await fetch(url);
                        const blob = await resp.blob();
                        return new Promise((resolve) => {
                            const r = new FileReader();
                            r.onloadend = () => resolve(r.result);
                            r.readAsDataURL(blob);
                        });
                    }
                """, src)
                if b64 and "base64," in b64:
                    raw = base64.b64decode(b64.split(",", 1)[1])
                    fname = f"meta_proper_spritesheet_{idx+1}.png"
                    fpath = out_dir / fname
                    fpath.write_bytes(raw)
                    downloaded.append((fpath, item["width"], item["height"]))
                    print(f"Saved: {fname} ({item['width']}x{item['height']}, {len(raw)} bytes)")
            except Exception as e:
                print(f"Download failed for item {idx}: {e}")
        
        await context.close()
        return downloaded

if __name__ == "__main__":
    asyncio.run(generate_sprites())
