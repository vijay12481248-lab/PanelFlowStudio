"""Exercise the real Setup UI and selector API against an isolated temporary project.

Start Vite on 5178, then run .venv/Scripts/python tools/qa_setup_selectors.py.
No request is sent to the user's engine; only loopback port 5189 is used.
"""
import json
from io import BytesIO
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import uvicorn

from engine.api.routers import panels, pages
from engine.database.models import Base, PageRecord, PanelRecord, ProjectRecord
from engine.database.session import get_db


def run():
    output = Path(__file__).resolve().parents[1] / "release" / "qa-setup-selectors"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="panelflow-selector-qa-") as temporary:
        workspace = Path(temporary).resolve()
        (workspace / "source").mkdir()
        (workspace / "panels").mkdir()
        image = Image.new("RGB", (800, 1200), "#0a0d16")
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 150, 600, 950), fill="#182945", outline="#9672ee", width=8)
        for y in range(150, 950, 80):
            draw.line((100, y, 600, y), fill="#314d75", width=2)
        for x in range(100, 600, 50):
            draw.line((x, 150, x, 950), fill="#314d75", width=2)
        draw.ellipse((230, 330, 470, 570), fill="#66c9c9", outline="#fff4de", width=6)
        draw.text((160, 780), "REAL CROP / 500 x 800 SOURCE PIXELS", fill="white")
        image.save(workspace / "source" / "page.png")
        second = Image.new("RGB", (800, 1200), "white")
        second_draw = ImageDraw.Draw(second)
        for y in (30, 630):
            second_draw.rectangle((30, y, 770, y + 540), fill="#e0e4ec", outline="black", width=8)
            second_draw.ellipse((200, y + 80, 600, y + 460), fill="#6385b0", outline="black", width=8)
        second.save(workspace / "source" / "page-two.png")
        image.crop((100, 150, 600, 950)).save(workspace / "panels" / "original.png")
        engine = create_engine(f"sqlite:///{workspace / 'qa.sqlite'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(ProjectRecord(id="qa", title="Isolated selector QA", source_type="LOCAL_FOLDER", workspace_path=str(workspace), rights_status="PUBLIC_DOMAIN"))
            db.add(PageRecord(id="page", project_id="qa", sequence=1, filename="page.png", sha256="fixture", width=800, height=1200))
            db.add(PageRecord(id="page-two", project_id="qa", sequence=2, filename="page-two.png", sha256="fixture-two", width=800, height=1200))
            db.add(PanelRecord(id="panel", project_id="qa", page_id="page", sequence=1, page_sequence=1, x=100, y=150, width=500, height=800, crop_filename="original.png", status="DETECTED"))
            db.commit()
        def session():
            with Session(engine) as db:
                yield db
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5178"], allow_methods=["*"], allow_headers=["*"])
        app.dependency_overrides[get_db] = session
        app.include_router(panels.router)
        app.include_router(pages.router)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=5189, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(200):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started, "isolated fixture server failed to start"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                tab = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
                errors = []
                failed_images = []
                tab.on("pageerror", lambda error: errors.append(str(error)))
                tab.on("response", lambda response: failed_images.append(response.url) if response.status >= 400 and ("/file" in response.url or "/selections" in response.url) else None)
                tab.goto("http://127.0.0.1:5178/qa/setup-selectors.html")
                tab.get_by_label("Panel selector editor").wait_for()
                tab.get_by_role("button", name="Show panels", exact=True).click()
                tab.wait_for_function("Array.from(document.images).every(img => img.complete && img.naturalWidth > 0)")
                assert tab.get_by_label("Source tools").count() == 0
                tab.screenshot(path=str(output / "setup-before.png"))
                editor = tab.get_by_label("Panel selector editor")
                view = editor.bounding_box()
                scale = min(view["width"] / 500, view["height"] / 800)
                corner = tab.get_by_label("Selector nw handle").bounding_box()
                start_x, start_y = corner["x"] + corner["width"] / 2, corner["y"] + corner["height"] / 2
                tab.mouse.move(start_x, start_y)
                tab.mouse.down()
                tab.mouse.move(start_x + 40 * scale, start_y + 50 * scale, steps=8)
                tab.mouse.up()
                with tab.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/selections")) as response:
                    tab.get_by_role("button", name="Save selectors", exact=True).click()
                assert response.value.status == 200, response.value.text()
                saved = response.value.json()[0]
                assert abs(saved["x"] - 140) <= 1 and abs(saved["y"] - 200) <= 1, saved
                # Save remounts on the new immutable crop filename.
                tab.wait_for_function("document.querySelector('[aria-label=\"Panel selector editor\"]').getAttribute('viewBox').startsWith('140 200')")
                tab.get_by_label("Split parts").fill("3")
                tab.get_by_role("button", name="Split vertically", exact=True).click()
                with tab.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/selections")) as split_response:
                    tab.get_by_role("button", name="Save selectors", exact=True).click()
                result = split_response.value.json()
                assert len(result) == 3 and sum(p["width"] for p in result) == 460, result
                inventory = json.loads((workspace / "panels" / "panels.json").read_text(encoding="utf-8"))
                assert len(inventory["panels"]) == 3
                tab.get_by_role("button", name="Edit panel 3", exact=True).wait_for()
                tab.screenshot(path=str(output / "setup-after-split.png"))
                shape_results = []
                for tool in ("Polygon", "Pen"):
                    box = tab.get_by_label("Panel selector editor").bounding_box()
                    selected = tab.get_by_label("Panel selector editor").get_attribute("viewBox").split()
                    _, _, width, height = map(float, selected)
                    factor = min(box["width"] / width, box["height"] / height)
                    left = box["x"] + (box["width"] - width * factor) / 2
                    top = box["y"] + (box["height"] - height * factor) / 2
                    vertices = [(left + width * factor * .2, top + height * factor * .2),
                                (left + width * factor * .8, top + height * factor * .2),
                                (left + width * factor * .8, top + height * factor * .8)]
                    tab.get_by_role("button", name=tool, exact=True).click()
                    if tool == "Polygon":
                        for x, y in vertices:
                            tab.mouse.click(x, y)
                    else:
                        tab.mouse.move(*vertices[0]); tab.mouse.down()
                        for x, y in vertices[1:]:
                            tab.mouse.move(x, y)
                        tab.mouse.up()
                    tab.get_by_role("button", name="Finish shape", exact=True).click()
                    original = tab.get_by_label("Active selector").locator("option").first.get_attribute("value")
                    tab.get_by_label("Active selector").select_option(original)
                    tab.get_by_role("button", name="Delete selector", exact=True).click()
                    with tab.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/selections")) as shape_response:
                        tab.get_by_role("button", name="Save selectors", exact=True).click()
                    assert shape_response.value.status == 200, shape_response.value.text()
                    shape = shape_response.value.json()[0]
                    assert len(json.loads(shape["polygon_json"])) >= 3
                    crop = tab.request.get(f"http://127.0.0.1:5189/api/projects/qa/panels/panel/file?v={shape['crop_filename']}")
                    assert crop.headers["content-type"] == "image/png"
                    with Image.open(BytesIO(crop.body())) as mask:
                        assert mask.mode == "RGBA" and mask.getextrema()[3] == (0, 255)
                    shape_results.append({"tool": tool, "panel": shape})
                    tab.wait_for_function("Array.from(document.images).every(img => img.complete && img.naturalWidth > 0)")
                tab.screenshot(path=str(output / "setup-polygon.png"))
                tab.get_by_role("button", name="Add panel to timeline", exact=True).click()
                tab.get_by_label("Video composition workspace").wait_for()
                assert tab.get_by_title("Resize Corner (NW)").count() == 0
                assert tab.get_by_label("Setup tools").count() == 0
                tab.screenshot(path=str(output / "player-preview.png"))
                tab.get_by_role("button", name="Setup", exact=True).click()
                tab.get_by_label("Panel selector editor").wait_for()
                tab.get_by_role("tab", name="Pages", exact=True).click()
                tab.get_by_label("Setup zoom", exact=True).select_option("width")
                region = tab.get_by_role("region", name="Current source page", exact=True)
                assert region.count() == 1
                assert region.evaluate("el => el.scrollHeight > el.clientHeight"), "Pages must scroll rather than fit a tall page into a tiny thumbnail"
                tab.screenshot(path=str(output / "setup-pages.png"))
                tab.get_by_role("button", name="Next setup page").click()
                assert tab.get_by_role("region", name="Current source page", exact=True).get_attribute("data-page-id") == "page-two"
                assert tab.get_by_role("button", name="Next setup page").is_disabled()
                with tab.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/pages/page-two/detect-panels")) as detection:
                    tab.get_by_role("button", name="Auto Detect", exact=True).click()
                assert detection.value.status == 200, detection.value.text()
                detected_panels = detection.value.json()
                assert len(detected_panels) >= 1
                tab.get_by_role("button", name="Edit panel 1", exact=True).wait_for()
                tab.get_by_role("tab", name="Both", exact=True).click()
                assert tab.get_by_role("region", name="Current source page", exact=True).count() == 1
                tab.get_by_label("Panel selector editor").wait_for()
                divider = tab.get_by_role("separator", name="Resize page and panel views")
                bounds = divider.bounding_box()
                tab.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
                tab.mouse.down(); tab.mouse.move(bounds["x"] + 100, bounds["y"] + bounds["height"] / 2, steps=8); tab.mouse.up()
                assert float(divider.get_attribute("aria-valuenow")) > 50
                divider.press("Home"); assert divider.get_attribute("aria-valuenow") == "25"
                divider.press("End"); assert divider.get_attribute("aria-valuenow") == "75"
                divider.dblclick()
                if len(detected_panels) > 1:
                    tab.get_by_role("button", name="Page panel 2", exact=True).click()
                    assert tab.get_by_role("button", name="Edit panel 2", exact=True).get_attribute("aria-pressed") == "true"
                    tab.get_by_role("button", name="Edit panel 1", exact=True).click()
                    assert tab.get_by_role("button", name="Page panel 1", exact=True).get_attribute("aria-pressed") == "true"
                tab.screenshot(path=str(output / "setup-both.png"))
                page_surface = tab.get_by_label("Page selector editor")
                page_box = page_surface.bounding_box()
                page_scale = page_box["width"] / 800
                handle = page_surface.get_by_label("Selector nw handle").bounding_box()
                hx, hy = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
                tab.mouse.move(hx, hy); tab.mouse.down(); tab.mouse.move(hx + 10 * page_scale, hy + 10 * page_scale, steps=5); tab.mouse.up()
                left_x = page_surface.locator('g[data-selected-panel="true"] rect').first.get_attribute("x")
                right_x = tab.get_by_label("Panel selector editor").locator("g rect").first.get_attribute("x")
                assert left_x == right_x, (left_x, right_x)
                with tab.expect_response(lambda response: response.request.method == "PUT" and response.url.endswith("/selections")) as both_save:
                    tab.get_by_role("button", name="Save selectors", exact=True).click()
                assert both_save.value.status == 200, both_save.value.text()
                tab.get_by_role("tab", name="Pages", exact=True).click()
                tab.get_by_role("button", name="Page panel 1", exact=True).dblclick()
                assert tab.get_by_role("tab", name="Panels", exact=True).get_attribute("aria-selected") == "true"
                assert tab.get_by_role("region", name="Current source page", exact=True).count() == 0
                tab.get_by_role("tab", name="Pages", exact=True).click()
                tab.get_by_role("button", name="Previous setup page").click()
                assert tab.get_by_role("region", name="Current source page", exact=True).get_attribute("data-page-id") == "page"
                tab.get_by_role("tab", name="Both", exact=True).click()
                for width, height in [(1024, 768), (1920, 1080)]:
                    tab.set_viewport_size({"width": width, "height": height})
                    tab.wait_for_timeout(100)
                    assert tab.get_by_label("Panel selector editor").bounding_box()["height"] >= 120
                    assert tab.evaluate("document.documentElement.scrollWidth <= innerWidth"), "horizontal page overflow"
                    tab.screenshot(path=str(output / f"setup-{width}.png"))
                assert errors == [], errors
                assert failed_images == [], failed_images
                (output / "results.json").write_text(json.dumps({"resize": saved, "split": result, "shapes": shape_results, "auto_detected_panels": len(detected_panels), "three_views": True, "pagination": True, "splitter": True, "browser_errors": errors, "failed_images": failed_images, "viewports": [1440, 1024, 1920]}, indent=2), encoding="utf-8")
                browser.close()
                print(f"Real browser + API acceptance passed. Evidence: {output}")
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            engine.dispose()


if __name__ == "__main__":
    run()
