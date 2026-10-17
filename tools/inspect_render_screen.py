import sys
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    page = b.new_page()
    page.on("console", lambda msg: print(f"[BROWSER CONSOLE {msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"[BROWSER ERROR] {err}"))
    page.on("response", lambda res: print(f"[NET {res.status}] {res.url}") if "/api/" in res.url else None)

    page.goto('http://localhost:5173')
    page.wait_for_selector('text=PanelFlow Studio', timeout=5000)
    page.locator("h3:has-text('Lumina: Chapter 1')").first.click()
    page.wait_for_selector('text=Production Renderer', timeout=5000)
    import time
    time.sleep(2)
    print('H1 headers:', page.locator('h1').all_inner_texts())
    print('H2 headers:', page.locator('h2').all_inner_texts())
    print('Render Screen HTML contains video:', '<video' in page.content())
    print('Render Screen HTML contains RENDER VERIFIED:', 'RENDER VERIFIED' in page.content())
    
    rows = page.locator("tbody tr").all()
    print(f"Total render history rows in UI: {len(rows)}")
    for i, r in enumerate(rows):
        print(f"Row {i}: {r.inner_text()}")

    page.screenshot(path='output/acceptance_qa_desktop/inspect_now.png')
    b.close()
