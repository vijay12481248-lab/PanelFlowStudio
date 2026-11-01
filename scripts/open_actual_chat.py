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

async def open_exact_chat():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(browser_ai_bridge.profile_dir),
            headless=True,
            viewport={"width": 1440, "height": 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating to https://www.meta.ai/...")
        await page.goto("https://www.meta.ai/", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click on the chat titled "2D video game character sprit..." in the sidebar
        chat_item = page.locator("text='2D video game character sprit'").first
        if await chat_item.is_visible():
            print("Found '2D video game character sprit' in history! Clicking it...")
            await chat_item.click()
            await page.wait_for_timeout(4000)
        else:
            print("Chat item not visible directly, searching sidebar...")
            links = await page.locator("a[href*='/c/']").all()
            for l in links:
                t = await l.inner_text()
                if "2D video game" in t:
                    print(f"Clicking link: {t}")
                    await l.click()
                    await page.wait_for_timeout(4000)
                    break

        print("Current URL:", page.url)
        await page.screenshot(path="E:/VIJAY SEKAR/PanelFlow Studio/output/meta_actual_chat.png")
        print("Saved screenshot of the actual chat: meta_actual_chat.png")
        
        # Extract all images from this specific chat
        chat_imgs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img'))
                .map(i => ({
                    src: i.currentSrc || i.src || '',
                    w: i.naturalWidth,
                    h: i.naturalHeight
                }))
                .filter(x => x.src.includes('fbcdn.net') && x.w > 100);
        }""")
        
        print(f"Found {len(chat_imgs)} images in this chat:")
        for idx, item in enumerate(chat_imgs):
            print(f"[{idx}] {item['w']}x{item['h']} -> {item['src'][:80]}")
            
            b64 = await page.evaluate("""async (url) => {
                const resp = await fetch(url);
                const blob = await resp.blob();
                return new Promise((resolve) => {
                    const r = new FileReader();
                    r.onloadend = () => resolve(r.result);
                    r.readAsDataURL(blob);
                });
            }""", item["src"])
            
            if b64 and "base64," in b64:
                raw_bytes = base64.b64decode(b64.split(",", 1)[1])
                im = Image.open(io.BytesIO(raw_bytes))
                dest = Path(f"C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a/actual_meta_sprite_{idx+1}.png")
                im.save(dest, "PNG")
                print(f"Saved REAL chat image to: {dest.name} ({im.size[0]}x{im.size[1]})")

        await context.close()

if __name__ == "__main__":
    asyncio.run(open_exact_chat())
