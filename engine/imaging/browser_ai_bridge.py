"""Browser AI Bridge for PanelFlow Studio.



Interacts with web-based AI tools (ChatGPT, Google Gemini, Meta AI, Claude, Midjourney web,

and custom URL prompt interfaces) using a managed, persistent browser session to input prompts,

execute generations, and quickly and precisely extract generated images and responses.

"""



from __future__ import annotations



import asyncio

import base64

import hashlib

import io

import logging

import os

import re

import time

import uuid

from dataclasses import dataclass, field

from pathlib import Path

from typing import Any, Dict, List, Optional, Set, Tuple

from urllib.parse import urlparse



from PIL import Image

from pydantic import BaseModel, Field



logger = logging.getLogger("panelflow.browser_ai_bridge")





class ExtractedImage(BaseModel):

    asset_id: str

    filename: str

    file_path: str

    url: str

    width: int

    height: int

    byte_size: int

    mime_type: str = "image/png"

    sha256: str





class BrowserBridgeResult(BaseModel):

    success: bool

    platform: str

    url: str

    prompt: str

    text_response: str = ""

    images: List[ExtractedImage] = Field(default_factory=list)

    execution_time_sec: float = 0.0

    error: Optional[str] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)





@dataclass

class PlatformPreset:

    id: str

    name: str

    default_url: str

    url_patterns: List[str]

    input_selectors: List[str]

    submit_selectors: List[str]

    stop_selectors: List[str]

    response_selectors: List[str]

    image_selectors: List[str]





SUPPORTED_PRESETS: List[PlatformPreset] = [

    PlatformPreset(

        id="chatgpt",

        name="ChatGPT / DALL-E",

        default_url="https://chatgpt.com",

        url_patterns=["chatgpt.com", "chat.openai.com"],

        input_selectors=[

            "#prompt-textarea",

            "div[contenteditable='true']#prompt-textarea",

            "div[contenteditable='true'][data-placeholder]",

            "textarea[data-id='root']",

            "div[contenteditable='true']",

            "textarea",

        ],

        submit_selectors=[

            "button[data-testid='send-button']",

            "button[aria-label*='Send' i]",

            "button[aria-label*='Submit' i]",

            "button.send-button",

        ],

        stop_selectors=[

            "button[data-testid='stop-button']",

            "button[aria-label*='Stop' i]",

            ".streaming",

        ],

        response_selectors=[

            "div[data-message-author-role='assistant']",

            "article[data-testid*='conversation-turn']",

            ".markdown",

        ],

        image_selectors=[

            "div[data-message-author-role='assistant'] img",

            "article img",

            "img[alt*='Generated' i]",

            "img[src*='oaiusercontent.com']",

        ],

    ),

    PlatformPreset(

        id="gemini",

        name="Google Gemini / Imagen",

        default_url="https://gemini.google.com",

        url_patterns=["gemini.google.com"],

        input_selectors=[

            "rich-textarea .ql-editor",

            "div[contenteditable='true'][role='textbox']",

            "rich-textarea textarea",

            "textarea.textarea",

            "div[contenteditable='true']",

            "textarea",

        ],

        submit_selectors=[

            "button[aria-label*='Send' i]",

            "button.send-button",

            "button[mattooltip*='Submit' i]",

            "button[aria-label*='Submit' i]",

        ],

        stop_selectors=[

            "button[aria-label*='Stop' i]",

            ".loading-spinner",

            "mat-progress-spinner",

        ],

        response_selectors=[

            ".model-response-text",

            "message-content",

            "model-response",

            ".response-content",

        ],

        image_selectors=[

            "generated-image img",

            "model-response img",

            "img[src*='googleusercontent.com']",

            "img[src*='blob:']",

        ],

    ),

    PlatformPreset(

        id="meta_ai",

        name="Meta AI / Imagine",

        default_url="https://www.meta.ai/ai-image-generator/",

        url_patterns=["meta.ai"],

        input_selectors=[

            "textarea[placeholder*='Describe' i]",

            "textarea[placeholder*='Imagine' i]",

            "textarea[placeholder*='Ask' i]",

            "div[role='textbox']",

            "div[contenteditable='true']",

            "input[type='text']:not([disabled])",

            "textarea",

        ],

        submit_selectors=[

            "button:has-text('Generate')",

            "button[aria-label*='Generate' i]",

            "button:has-text('Imagine')",

            "div[aria-label*='Send' i]",

            "button[aria-label*='Send' i]",

            "button[type='submit']",

        ],

        stop_selectors=[

            "button[aria-label*='Stop' i]",

            "div[aria-label*='Stop' i]",

            ".loading",

            ".spinner",

        ],

        response_selectors=[

            "div[data-testid*='message' i]",

            "div[role='article']",

            ".x1n2onr6",

        ],

        image_selectors=[

            "img[src*='fbcdn.net']",

            "img[src*='instagram']",

            "img[alt*='Generated' i]",

            "div[role='img'] img",

        ],

    ),

    PlatformPreset(

        id="claude",

        name="Anthropic Claude",

        default_url="https://claude.ai",

        url_patterns=["claude.ai"],

        input_selectors=[

            "div[contenteditable='true']",

            "fieldset div[contenteditable='true']",

            "div[role='textbox']",

            "textarea",

        ],

        submit_selectors=[

            "button[aria-label*='Send' i]",

            "button[data-testid='send-button']",

        ],

        stop_selectors=[

            "button[aria-label*='Stop' i]",

        ],

        response_selectors=[

            "div[data-is-streaming]",

            ".font-claude-message",

            ".standard-markdown",

        ],

        image_selectors=[

            "img",

        ],

    ),

]



UNIVERSAL_PRESET = PlatformPreset(

    id="universal",

    name="Universal Web Tool",

    default_url="",

    url_patterns=[],

    input_selectors=[

        "textarea:not([disabled])",

        "div[contenteditable='true']",

        "[role='textbox']",

        "input[type='text']:not([disabled])",

    ],

    submit_selectors=[

        "button[type='submit']",

        "button:has-text('Send')",

        "button:has-text('Submit')",

        "button:has-text('Generate')",

        "button:has-text('Imagine')",

        "button[aria-label*='Send' i]",

        "button[aria-label*='Submit' i]",

        "button[aria-label*='Generate' i]",

        "button[data-testid*='send' i]",

        "button[id*='send' i]",

        "button.send-button",

    ],

    stop_selectors=[

        "button:has-text('Stop')",

        "button[aria-label*='Stop' i]",

        "button[data-testid*='stop' i]",

        "[id*='stop']",

        ".loading",

        ".spinner",

    ],

    response_selectors=[

        "[data-message-author-role='assistant']",

        "[role='article']",

        ".response",

        ".output",

        ".result",

        "[id*='response']",

        "[class*='response']",

    ],

    image_selectors=[

        "img[src^='blob:']",

        "img[src^='data:image']",

        "img:not([width='1']):not([height='1'])",

    ],

)





def get_default_profile_dir() -> Path:

    """Returns the persistent browser profile directory to maintain user logins."""

    home = Path.home()

    base = home / ".panelflow" / "browser_sessions" / "default"

    base.mkdir(parents=True, exist_ok=True)

    return base





def detect_platform_preset(url: str) -> PlatformPreset:

    """Detects matching platform preset from URL, or returns Universal preset."""

    if not url:

        return UNIVERSAL_PRESET

    url_lower = url.lower()

    for preset in SUPPORTED_PRESETS:

        for pat in preset.url_patterns:

            if pat in url_lower:

                return preset

    return UNIVERSAL_PRESET





class BrowserAIBridge:

    """Automates browser interactions to submit prompts to AI web tools and extract results."""



    def __init__(self, profile_dir: Optional[Path] = None):

        self.profile_dir = profile_dir or get_default_profile_dir()

        self._active_contexts: List[Any] = []



    def get_status(self) -> Dict[str, Any]:

        """Returns browser availability and profile information."""

        chrome_available = False

        edge_available = False

        playwright_available = False



        try:

            import playwright

            playwright_available = True

        except ImportError:

            pass



        # Check installed browser binaries

        candidates = [

            (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome"),

            (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "chrome"),

            (os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"), "chrome"),

            (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "msedge"),

            (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "msedge"),

        ]

        for p, browser_type in candidates:

            if os.path.exists(p):

                if browser_type == "chrome":

                    chrome_available = True

                elif browser_type == "msedge":

                    edge_available = True



        return {

            "playwright_installed": playwright_available,

            "chrome_detected": chrome_available,

            "edge_detected": edge_available,

            "preferred_channel": "chrome" if chrome_available else ("msedge" if edge_available else "chromium"),

            "profile_dir": str(self.profile_dir),

            "presets": [

                {"id": p.id, "name": p.name, "default_url": p.default_url}

                for p in SUPPORTED_PRESETS

            ],

        }



    def launch_interactive_session(self, url: str) -> Dict[str, Any]:

        """

        Launches a visible native browser window so the user can log into their AI account

        (OpenAI, Google, Meta, etc.). The login is saved in the persistent user profile.

        """

        import subprocess



        candidates = [

            r"C:\Program Files\Google\Chrome\Application\chrome.exe",

            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",

            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),

            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",

            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",

        ]

        exe_path = None

        for cand in candidates:

            if os.path.exists(cand):

                exe_path = cand

                break



        target_url = url or "https://www.meta.ai/ai-image-generator/"



        if exe_path:

            args = [

                exe_path,

                f"--user-data-dir={self.profile_dir}",

                "--no-first-run",

                "--no-default-browser-check",

                target_url,

            ]

            proc = subprocess.Popen(args)

            return {

                "success": True,

                "message": "Interactive browser session launched. Log in to your AI account. Session state will be saved.",

                "profile_dir": str(self.profile_dir),

                "pid": proc.pid,

                "url": target_url,

            }

        else:

            from playwright.sync_api import sync_playwright

            p = sync_playwright().start()

            context = p.chromium.launch_persistent_context(

                user_data_dir=str(self.profile_dir),

                headless=False,

                viewport={"width": 1280, "height": 850},

            )

            page = context.new_page() if not context.pages else context.pages[0]

            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            return {

                "success": True,

                "message": "Interactive browser session launched via Playwright. Log in to your AI account.",

                "profile_dir": str(self.profile_dir),

                "url": target_url,

            }



    async def execute_prompt_async(

        self,

        url: str,

        prompt: str,

        extract_type: str = "all",  # "images", "text", "all"

        output_dir: Optional[Path] = None,

        headless: bool = True,

        timeout_sec: float = 120.0,

        project_id: Optional[str] = None,

    ) -> BrowserBridgeResult:

        """Runs the synchronous execute_prompt in an async executor thread."""

        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(

            None,

            lambda: self.execute_prompt(

                url=url,

                prompt=prompt,

                extract_type=extract_type,

                output_dir=output_dir,

                headless=headless,

                timeout_sec=timeout_sec,

                project_id=project_id,

            ),

        )



    def execute_prompt(

        self,

        url: str,

        prompt: str,

        extract_type: str = "all",  # "images", "text", "all"

        output_dir: Optional[Path] = None,

        headless: bool = True,

        timeout_sec: float = 120.0,

        project_id: Optional[str] = None,

    ) -> BrowserBridgeResult:

        """

        Navigates to URL, inputs the prompt, triggers execution, and extracts results fast and accurately.

        """

        start_time = time.monotonic()

        preset = detect_platform_preset(url)

        dest_dir = output_dir or (Path("output/web_ai") if not project_id else Path(f"workspaces/{project_id}/assets/web_ai"))

        dest_dir.mkdir(parents=True, exist_ok=True)



        from playwright.sync_api import sync_playwright



        status = self.get_status()

        channel = status["preferred_channel"]



        with sync_playwright() as playwright:

            # Launch persistent browser context to retain logged-in sessions

            context = playwright.chromium.launch_persistent_context(

                user_data_dir=str(self.profile_dir),

                channel=channel if channel in ("chrome", "msedge") else None,

                headless=headless,

                viewport={"width": 1366, "height": 900},

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--no-first-run",

                    "--no-default-browser-check",

                ],

            )



            try:

                page = context.new_page() if not context.pages else context.pages[0]

                page.set_default_timeout(min(45000, int(timeout_sec * 1000)))



                logger.info("Navigating to %s (Platform: %s)", url, preset.name)

                page.goto(url, wait_until="domcontentloaded", timeout=45000)



                # 1. Snapshot existing images on page so we only capture NEW images

                existing_img_srcs: Set[str] = set()

                try:

                    existing_img_srcs = set(page.evaluate("""

                        () => Array.from(document.querySelectorAll('img')).map(el => el.currentSrc || el.src).filter(Boolean)

                    """))

                except Exception:

                    pass



                # 2. Locate input element

                input_elem = self._locate_input(page, preset)

                if not input_elem:

                    raise RuntimeError(

                        f"Could not locate prompt input element on {preset.name} ({url}). "

                        "The page may require logging in first. Use 'Open Browser' to log in."

                    )



                # 3. Enter prompt into input field

                self._inject_prompt(page, input_elem, prompt)



                # 4. Submit prompt

                submitted = self._submit_prompt(page, input_elem, preset)

                if not submitted:

                    raise RuntimeError(f"Could not trigger prompt submission on {preset.name}.")



                # 5. Wait for generation to start and complete

                self._wait_for_completion(page, preset, timeout_sec=timeout_sec)



                # 6. Extract results (Images and/or Text)

                extracted_images: List[ExtractedImage] = []

                response_text = ""



                if extract_type in ("images", "all"):

                    extracted_images = self._extract_images(page, preset, existing_img_srcs, dest_dir, project_id)



                if extract_type in ("text", "all"):

                    response_text = self._extract_text(page, preset)



                elapsed = round(time.monotonic() - start_time, 2)

                logger.info("Browser AI Bridge completed in %ss. Extracted %d images.", elapsed, len(extracted_images))



                return BrowserBridgeResult(

                    success=True,

                    platform=preset.id,

                    url=url,

                    prompt=prompt,

                    text_response=response_text,

                    images=extracted_images,

                    execution_time_sec=elapsed,

                    metadata={"preset_name": preset.name, "output_dir": str(dest_dir)},

                )



            except Exception as exc:

                elapsed = round(time.monotonic() - start_time, 2)

                logger.exception("Browser AI Bridge error: %s", exc)

                return BrowserBridgeResult(

                    success=False,

                    platform=preset.id,

                    url=url,

                    prompt=prompt,

                    execution_time_sec=elapsed,

                    error=str(exc),

                )

            finally:

                try:

                    context.close()

                except Exception:

                    pass



    def _locate_input(self, page: Any, preset: PlatformPreset) -> Optional[Any]:

        """Tries preset input selectors, then falls back to universal dynamic discovery."""

        # 1. Preset selectors

        for sel in preset.input_selectors:

            try:

                locator = page.locator(sel).first

                if locator.is_visible(timeout=800):

                    return locator

            except Exception:

                continue



        # 2. Universal dynamic search for prominent input

        try:

            for fallback_sel in UNIVERSAL_PRESET.input_selectors:

                elements = page.locator(fallback_sel).all()

                for elem in elements:

                    try:

                        if elem.is_visible(timeout=300):

                            box = elem.bounding_box()

                            if box and box["width"] > 80 and box["height"] > 20:

                                return elem

                    except Exception:

                        continue

        except Exception:

            pass



        return None



    def _inject_prompt(self, page: Any, elem: Any, prompt: str) -> None:

        """Types prompt cleanly and dispatches events so React/Vue/Angular registers the input."""

        elem.scroll_into_view_if_needed()

        elem.click()

        time.sleep(0.05)



        is_contenteditable = elem.evaluate("el => el.isContentEditable || el.getAttribute('role') === 'textbox'")



        if is_contenteditable:

            # Clear existing content if any

            page.keyboard.press("Control+A")

            page.keyboard.press("Backspace")

            # Insert text cleanly

            page.keyboard.insert_text(prompt)

            # Dispatch synthetic input event to ensure state bindings update

            elem.evaluate("el => el.dispatchEvent(new Event('input', { bubbles: true }))")

        else:

            try:

                elem.fill(prompt)

            except Exception:

                elem.click()

                page.keyboard.press("Control+A")

                page.keyboard.press("Backspace")

                page.keyboard.insert_text(prompt)

            elem.evaluate("el => el.dispatchEvent(new Event('input', { bubbles: true }))")



        time.sleep(0.1)



    def _submit_prompt(self, page: Any, input_elem: Any, preset: PlatformPreset) -> bool:

        """Clicks submit button or presses Enter."""

        # 1. Look for enabled submit button

        for sel in preset.submit_selectors + UNIVERSAL_PRESET.submit_selectors:

            try:

                btn = page.locator(sel).first

                if btn.is_visible(timeout=400) and btn.is_enabled(timeout=400):

                    btn.click()

                    return True

            except Exception:

                continue



        # 2. Fallback: Press Enter on the input element

        try:

            input_elem.press("Enter")

            return True

        except Exception:

            page.keyboard.press("Enter")

            return True



    def _wait_for_completion(self, page: Any, preset: PlatformPreset, timeout_sec: float) -> None:

        """

        Event-driven fast polling:

        1. Detects start of generation (stop button appears or state active).

        2. Detects completion (stop button disappears, or DOM content stabilizes).

        """

        deadline = time.monotonic() + timeout_sec

        started = False



        # Phase 1: Wait up to 10s for generation to start

        start_wait_deadline = time.monotonic() + min(12.0, timeout_sec / 2)

        while time.monotonic() < start_wait_deadline:

            for stop_sel in preset.stop_selectors:

                try:

                    if page.locator(stop_sel).first.is_visible(timeout=100):

                        started = True

                        break

                except Exception:

                    continue

            if started:

                break

            time.sleep(0.1)



        # Phase 2: Wait for generation to complete (stop button disappears or output stabilizes)

        stable_count = 0

        last_body_len = 0



        while time.monotonic() < deadline:

            # Check if any stop indicator is still visible

            still_generating = False

            for stop_sel in preset.stop_selectors:

                try:

                    if page.locator(stop_sel).first.is_visible(timeout=100):

                        still_generating = True

                        break

                except Exception:

                    continue



            if not still_generating and started:

                # Give a 0.5s settle window

                time.sleep(0.5)

                break



            # Mutation length stabilization check

            try:

                curr_len = len(page.content())

                if curr_len == last_body_len and curr_len > 20:

                    stable_count += 1

                    if stable_count >= 5:  # ~0.5s of total DOM stability

                        break

                else:

                    stable_count = 0

                    last_body_len = curr_len

            except Exception:

                pass



            time.sleep(0.1)



    def _extract_images(

        self,

        page: Any,

        preset: PlatformPreset,

        existing_srcs: Set[str],

        output_dir: Path,

        project_id: Optional[str] = None,

    ) -> List[ExtractedImage]:

        """

        Locates newly generated images on the page, captures/downloads them,

        verifies them, and saves them to disk and project records.

        """

        extracted: List[ExtractedImage] = []



        # Find all <img> tags currently in the document

        img_data_list = page.evaluate("""

            () => {

                const results = [];

                const imgs = document.querySelectorAll('img');

                for (let i = 0; i < imgs.length; i++) {

                    const img = imgs[i];

                    const rect = img.getBoundingClientRect();

                    const src = img.currentSrc || img.src || '';

                    if (!src) continue;

                    // Filter out tiny icons, emojis, tracking pixels

                    const w = img.naturalWidth || rect.width;

                    const h = img.naturalHeight || rect.height;

                    if (w >= 120 && h >= 120) {

                        results.push({

                            src: src,

                            width: Math.round(w),

                            height: Math.round(h),

                            alt: img.alt || '',

                            className: img.className || '',

                        });

                    }

                }

                return results;

            }

        """)



        # Identify newly generated images

        new_candidates = [

            item for item in img_data_list

            if item["src"] not in existing_srcs and not self._is_ignored_icon(item["src"])

        ]



        # If no new image found via set difference, take the largest recent image in response container

        if not new_candidates and img_data_list:

            sorted_by_size = sorted(img_data_list, key=lambda x: x["width"] * x["height"], reverse=True)

            if sorted_by_size and sorted_by_size[0]["width"] >= 256:

                new_candidates = [sorted_by_size[0]]



        logger.info("Found %d candidate image(s) for extraction", len(new_candidates))



        for idx, item in enumerate(new_candidates[:6]):  # extract up to 6 generated images

            src = item["src"]

            raw_bytes: Optional[bytes] = None



            # Case A: Data URL (base64)

            if src.startswith("data:image/"):

                try:

                    header, b64_data = src.split(",", 1)

                    raw_bytes = base64.b64decode(b64_data)

                except Exception as e:

                    logger.warning("Failed to decode data URL: %s", e)



            # Case B: Blob URL or HTTP/HTTPS (Fetch within authenticated browser page context)

            if not raw_bytes and (src.startswith("blob:") or src.startswith("http")):

                try:

                    b64_res = page.evaluate("""

                        async (url) => {

                            try {

                                const resp = await fetch(url);

                                const blob = await resp.blob();

                                return new Promise((resolve, reject) => {

                                    const reader = new FileReader();

                                    reader.onloadend = () => resolve(reader.result);

                                    reader.onerror = reject;

                                    reader.readAsDataURL(blob);

                                });

                            } catch (e) {

                                return null;

                            }

                        }

                    """, src)

                    if b64_res and "base64," in b64_res:

                        _, b64_str = b64_res.split(",", 1)

                        raw_bytes = base64.b64decode(b64_str)

                except Exception as e:

                    logger.warning("Failed in-page fetch for image %s: %s", src[:60], e)



            # Case C: Element Screenshot fallback

            if not raw_bytes:

                try:

                    locator = page.locator(f"img[src='{src}']").first

                    if locator.is_visible(timeout=500):

                        raw_bytes = locator.screenshot(type="png")

                except Exception:

                    pass



            if not raw_bytes:

                continue



            # Verify image validity and dimensions via Pillow

            try:

                with Image.open(io.BytesIO(raw_bytes)) as pil_img:

                    pil_img.verify()

                with Image.open(io.BytesIO(raw_bytes)) as pil_img:

                    w, h = pil_img.size

                    img_format = (pil_img.format or "PNG").lower()

            except Exception as e:

                logger.warning("Invalid image bytes extracted: %s", e)

                continue



            # Save to disk

            asset_uuid = uuid.uuid4().hex[:12]

            filename = f"web_ai_{preset.id}_{asset_uuid}.{img_format}"

            out_file = output_dir / filename

            out_file.write_bytes(raw_bytes)

            sha = hashlib.sha256(raw_bytes).hexdigest()



            # Relative URL for web serving

            url_ref = f"/assets/web_ai/{filename}"

            if project_id:

                url_ref = f"/api/projects/{project_id}/assets/web_ai/{filename}"

                # Also register in Project DB if SessionLocal available

                try:

                    self._register_asset_in_db(project_id, out_file, filename, w, h, len(raw_bytes), sha, preset.id)

                except Exception as db_err:

                    logger.warning("Failed to register asset in DB: %s", db_err)



            extracted.append(

                ExtractedImage(

                    asset_id=f"ast_{asset_uuid}",

                    filename=filename,

                    file_path=str(out_file.resolve()),

                    url=url_ref,

                    width=w,

                    height=h,

                    byte_size=len(raw_bytes),

                    mime_type=f"image/{img_format}",

                    sha256=sha,

                )

            )



        return extracted



    def _extract_text(self, page: Any, preset: PlatformPreset) -> str:

        """Extracts the latest response text or markdown generated by the assistant."""

        for sel in preset.response_selectors + UNIVERSAL_PRESET.response_selectors:

            try:

                elements = page.locator(sel).all()

                if elements:

                    last_elem = elements[-1]

                    if last_elem.is_visible(timeout=300):

                        text = last_elem.inner_text().strip()

                        if text:

                            return text

            except Exception:

                continue



        # Fallback: get visible text of the conversation container or response paragraphs

        try:

            text = page.evaluate("""

                () => {

                    const candidates = [

                        ...document.querySelectorAll('[data-message-author-role="assistant"]'),

                        ...document.querySelectorAll('article'),

                        ...document.querySelectorAll('.response, .output, .result, [id*="response"]'),

                    ];

                    if (candidates.length > 0) {

                        const last = candidates[candidates.length - 1];

                        const t = last.innerText.trim();

                        if (t) return t;

                    }

                    const paragraphs = Array.from(document.querySelectorAll('p')).map(p => p.innerText.trim()).filter(Boolean);

                    if (paragraphs.length > 0) {

                        return paragraphs.join('\n');

                    }

                    return '';

                }

            """)

            if text:

                return text

        except Exception:

            pass

        return ""



    @staticmethod

    def _is_ignored_icon(src: str) -> bool:

        """Filters out tracking pixels, avatar icons, and badges."""

        s = src.lower()

        return any(

            x in s for x in [

                "avatar", "favicon", "logo", "icon", "badge",

                "emoji", "tracking", "pixel", ".svg", "profile"

            ]

        )



    @staticmethod

    def _register_asset_in_db(

        project_id: str,

        file_path: Path,

        filename: str,

        width: int,

        height: int,

        byte_size: int,

        sha256: str,

        platform: str,

    ) -> None:

        """Registers the extracted image as a project AssetRecord in SQLite."""

        try:

            from engine.database.session import SessionLocal

            from engine.database.models import AssetRecord



            with SessionLocal() as db:

                rel_path = f"assets/web_ai/{filename}"

                asset = AssetRecord(

                    id=f"ast_{uuid.uuid4().hex[:12]}",

                    project_id=project_id,

                    asset_type="web_ai_image",

                    filename=filename,

                    relative_path=rel_path,

                    content_type="image/png",

                    width=width,

                    height=height,

                    byte_size=byte_size,

                    sha256=sha256,

                    status="READY",

                    provenance={"platform": platform, "tool": "browser_ai_bridge"},

                )

                db.add(asset)

                db.commit()

        except Exception as e:

            logger.debug("Database asset record skip: %s", e)





# Global singleton instance

browser_ai_bridge = BrowserAIBridge()
