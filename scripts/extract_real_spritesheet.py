import asyncio
import base64
import time
from playwright.async_api import async_playwright
from pathlib import Path
import sys
from PIL import Image
import io

PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

TARGET_URL = "https://www.meta.ai/prompt/2594e052-dce5-476f-9348-0c23376b294a"

async def extract_real_generation():
    print(f"Opening chat: {TARGET_URL}")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(TARGET_URL, timeout=45000)
        
        # Wait up to 30 seconds for images to appear
        print("Waiting for generation to finish...")
        for i in range(15):
            await page.wait_for_timeout(2000)
            imgs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('img'))
                    .map(i => i.currentSrc || i.src || '')
                    .filter(u => u.includes('fbcdn.net') && (u.includes('.webp') || u.includes('.png') || u.includes('.jpeg') || u.includes('.jpg')));
            }""")
            print(f"Check {i+1}: found {len(imgs)} candidate image(s)")
            if len(imgs) >= 1:
                break
                
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_prompt_finished.png")
        print("Saved screenshot: meta_prompt_finished.png")
        
        # Extract the images
        valid_imgs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img'))
                .map(i => ({
                    src: i.currentSrc || i.src || '',
                    w: i.naturalWidth,
                    h: i.naturalHeight
                }))
                .filter(x => x.src.includes('fbcdn.net') && x.w > 150);
        }""")
        
        print(f"Total valid generated images: {len(valid_imgs)}")
        dest_dir = Path("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a")
        
        for idx, item in enumerate(valid_imgs):
            src = item["src"]
            b64 = await page.evaluate("""async (url) => {
                const resp = await fetch(url);
                const blob = await resp.blob();
                return new Promise((resolve) => {
                    const r = new FileReader();
                    r.onloadend = () => resolve(r.result);
                    r.readAsDataURL(blob);
                });
            }""", src)
            
            if b64 and "base64," in b64:
                raw_bytes = base64.b64decode(b64.split(",", 1)[1])
                im = Image.open(io.BytesIO(raw_bytes))
                dest = dest_dir / f"real_meta_spritesheet_{idx+1}.png"
                im.save(dest, "PNG")
                print(f"SUCCESS: Saved REAL spritesheet {dest.name} ({im.size[0]}x{im.size[1]})!")
                
        await context.close()

if __name__ == "__main__":
    asyncio.run(extract_real_generation())
