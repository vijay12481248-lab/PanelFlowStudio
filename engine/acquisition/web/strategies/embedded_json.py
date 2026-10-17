"""
Embedded structured JSON and framework hydration extraction strategy (Stage 7).
Parses JSON-LD, Next.js (__NEXT_DATA__), Nuxt (__NUXT__), and serialized reader state
without executing arbitrary JavaScript code.
"""
import json
import re
import time
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_collector import normalize_image_url
from engine.acquisition.web.discovery.page_classifier import IMAGE_EXTENSIONS

MANIFEST_KEY_HINTS = {"pages", "images", "files", "chapter_pages", "chapter_images", "slides", "assets", "page_list", "data"}


def is_image_url_like(val: Any) -> bool:
    if not isinstance(val, str) or len(val) < 5:
        return False
    lower = val.lower().split("?")[0]
    return any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS) or "image" in lower or "/page" in lower


def find_image_arrays_recursive(data: Any, found_lists: List[List[str]], current_depth: int = 0):
    """Recursively search dictionary/list tree for lists of image URLs."""
    if current_depth > 8:
        return

    if isinstance(data, dict):
        # Support baseUrl + chapter.hash + chapter.data pattern (e.g. MangaDex and At-Home style APIs)
        lowered_keys = {k.lower(): k for k in data.keys()}
        if "baseurl" in lowered_keys:
            base_url_val = data[lowered_keys["baseurl"]]
            ch_k = lowered_keys.get("chapter")
            if ch_k and isinstance(data[ch_k], dict):
                ch_dict = data[ch_k]
                h = ch_dict.get("hash")
                items = ch_dict.get("data") or ch_dict.get("dataSaver") or []
                if h and items and isinstance(items, list):
                    full_urls = [f"{base_url_val}/data/{h}/{fn}" for fn in items]
                    found_lists.append(full_urls)

        for k, v in data.items():
            if k.lower() in MANIFEST_KEY_HINTS and isinstance(v, list) and len(v) >= 2:
                # Check if list entries are image-like or dicts with url/src/file
                candidate_urls = []
                for item in v:
                    if isinstance(item, str) and is_image_url_like(item):
                        candidate_urls.append(item)
                    elif isinstance(item, dict):
                        for sub_k in ("url", "src", "file", "path", "image", "image_url"):
                            if sub_k in item and is_image_url_like(item[sub_k]):
                                candidate_urls.append(item[sub_k])
                                break
                if len(candidate_urls) >= 2:
                    found_lists.append(candidate_urls)

            find_image_arrays_recursive(v, found_lists, current_depth + 1)

    elif isinstance(data, list):
        for item in data:
            find_image_arrays_recursive(item, found_lists, current_depth + 1)


class EmbeddedJsonStrategy(BaseExtractionStrategy):
    @property
    def strategy_id(self) -> str:
        return "EMBEDDED_JSON"

    async def extract(
        self,
        url: str,
        html_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> StrategyResult:
        start_t = time.perf_counter()

        if not html_text:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="FAILED",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No HTML document provided for JSON analysis",
            )

        json_blobs: List[Any] = []

        # 0. Check if document itself is raw JSON
        trimmed = html_text.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                data = json.loads(trimmed)
                json_blobs.append(data)
            except Exception:
                pass

        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Parse <script type="application/json"> or <script type="application/ld+json">
        for script in soup.find_all("script", attrs={"type": re.compile(r"json", re.I)}):
            text = script.string
            if text and text.strip():
                try:
                    data = json.loads(text.strip())
                    json_blobs.append(data)
                except Exception:
                    pass

        # 2. Check Next.js __NEXT_DATA__
        next_tag = soup.find("script", id="__NEXT_DATA__")
        if next_tag and next_tag.string:
            try:
                data = json.loads(next_tag.string.strip())
                json_blobs.append(data)
            except Exception:
                pass

        # 3. Check inline window / JSON variable assignments
        for script in soup.find_all("script"):
            if script.get("src"):
                continue
            content = script.string or ""
            # Match assignments like: window.__INITIAL_STATE__ = {...}; or var chapterData = {...};
            matches = re.findall(r"(?:chapterData|chapter_images|pageData|initialState|__NUXT__)\s*=\s*({.*?});", content, re.DOTALL)
            for m in matches:
                try:
                    data = json.loads(m.strip())
                    json_blobs.append(data)
                except Exception:
                    pass

        # Search all discovered json objects for page lists
        found_url_lists: List[List[str]] = []
        for blob in json_blobs:
            find_image_arrays_recursive(blob, found_url_lists)

        if not found_url_lists:
            elapsed = (time.perf_counter() - start_t) * 1000
            return StrategyResult(
                strategy_id=self.strategy_id,
                status="LOW_CONFIDENCE",
                candidates=[],
                confidence=0.0,
                elapsed_ms=round(elapsed, 2),
                failure_reason="No embedded structured page manifests discovered in HTML",
            )

        # Pick the largest array of image URLs
        found_url_lists.sort(key=len, reverse=True)
        best_urls = found_url_lists[0]

        candidates: List[ImageCandidate] = []
        for idx, u in enumerate(best_urls, start=1):
            resolved = normalize_image_url(u, url)
            cand = ImageCandidate(
                url=u,
                resolved_url=resolved,
                dom_order=idx,
                content_score=0.95,
                score_reasons=["embedded-json-manifest-item", "structured-page-array"],
                source_strategies={self.strategy_id},
            )
            candidates.append(cand)

        count = len(candidates)
        conf = 0.98 if count >= 5 else 0.85

        elapsed = (time.perf_counter() - start_t) * 1000
        return StrategyResult(
            strategy_id=self.strategy_id,
            status="SUCCESS",
            candidates=candidates,
            metadata={"manifest_format": "EMBEDDED_JSON", "page_count": count},
            confidence=conf,
            elapsed_ms=round(elapsed, 2),
        )
