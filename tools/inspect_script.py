from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    page = b.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_selector('text=PanelFlow Studio', timeout=5000)
    page.locator("h3:has-text('Lumina: Chapter 1')").first.click()
    page.wait_for_selector('text=Production Renderer', timeout=5000)
    page.locator("button:has-text('Script')").first.click()
    page.wait_for_selector('text=Video Script Adaptation & Review', timeout=5000)
    time.sleep(1)
    edit_btns = page.locator("button:has-text('Edit')").all()
    print('Found Edit buttons:', len(edit_btns))
    for i, btn in enumerate(edit_btns[:3]):
        print(f'Button {i}: visible={btn.is_visible()}, text={btn.inner_text()}')

    if edit_btns:
        edit_btns[0].click()
        time.sleep(0.5)
        textarea = page.locator("textarea")
        print('Textarea visible:', textarea.is_visible())
        save_btn = page.locator("button:has-text('Save Line')")
        print('Save button visible:', save_btn.is_visible())
        save_btn.click()
        time.sleep(3)
        # Check navbar text
        nav_btns = page.locator("nav button, div.mb-6 button").all()
        print('Navbar buttons after save:')
        for nb in nav_btns:
            print(' -', nb.inner_text())

    b.close()
