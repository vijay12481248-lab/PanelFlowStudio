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

async def open_mechanic_chat():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        
        chat_item = page.get_by_text("Mechanic hero sprite sheet").first
        print("Clicking 'Mechanic hero sprite sheet' in sidebar...")
        await chat_item.click()
        await page.wait_for_timeout(4000)
        
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_mechanic_hero_chat.png")
        print("Saved meta_mechanic_hero_chat.png!")
        
        # Check text in the chat
        text = await page.evaluate("() => document.body.innerText")
        print("--- Text preview ---")
        for line in text.split("\n"):
            if any(w in line.lower() for w in ["sprite", "mechanic", "grid", "hero", "image", "frame"]):
                print(line[:120])
                
        # Find images in this chat
        imgs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img'))
                .map(i => ({
                    src: i.currentSrc || i.src || '',
                    w: i.naturalWidth,
                    h: i.naturalHeight
                }))
                .filter(x => x.src.includes('fbcdn.net') && (x.w > 200 || x.src.includes('105495')));
        }""")
        
        print(f"Found {len(imgs)} candidate images in Mechanic hero chat:")
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
                raw_bytes = base64.b64decode(b64.split(",", 1)[1])
                im = Image.open(io.BytesIO(raw_bytes))
                dest = dest_dir / f"real_mechanic_spritesheet_{idx+1}.png"
                im.save(dest, "PNG")
                print(f"SAVED: {dest.name} ({im.size[0]}x{im.size[1]})!")

        await context.close()

if __name__ == "__main__":
    asyncio.run(open_mechanic_chat())
