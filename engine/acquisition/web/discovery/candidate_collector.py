"""
DOM Candidate Collector for extracting image candidate representations with full provenance.
Inspects src, srcset, picture/source, and lazy-loading attributes (data-src, data-original, etc.).
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
from engine.acquisition.web.models.image_candidate import ImageCandidate

LAZY_ATTR_CANDIDATES = [
    "data-src",
    "data-lazy-src",
    "data-original",
    "data-url",
    "data-image",
    "data-file",
    "data-full-url",
    "data-orig-file",
    "data-lazy",
    "data-echo",
    "data-srcset",
    "srcset",
    "src",
]


def parse_srcset_best_url(srcset: str, base_url: str) -> Optional[str]:
    """Parse srcset descriptor and pick the highest resolution candidate."""
    if not srcset:
        return None
    candidates = []
    # e.g. "image-320w.jpg 320w, image-480w.jpg 480w, image-800w.jpg 800w"
    entries = [e.strip() for e in srcset.split(",") if e.strip()]
    for entry in entries:
        parts = entry.split()
        if not parts:
            continue
        u = parts[0]
        desc = parts[1] if len(parts) > 1 else "1x"
        weight = 1
        if desc.endswith("w"):
            try:
                weight = int(desc[:-1])
            except ValueError:
                weight = 1
        elif desc.endswith("x"):
            try:
                weight = int(float(desc[:-1]) * 1000)
            except ValueError:
                weight = 1000
        candidates.append((u, weight))

    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return urljoin(base_url, candidates[0][0])
    return None


def normalize_image_url(raw_url: str, base_url: str) -> str:
    """Canonicalize relative and protocol-relative image URLs."""
    raw = raw_url.strip()
    if raw.startswith("//"):
        parsed_base = urlparse(base_url)
        return f"{parsed_base.scheme}:{raw}"
    return urljoin(base_url, raw)


class CandidateCollector:
    """
    Extracts image candidates from HTML DOM structures.
    """

    def collect(self, soup: BeautifulSoup, base_url: str, container_tag: Optional[Tag] = None) -> List[ImageCandidate]:
        candidates: List[ImageCandidate] = []
        scope = container_tag if container_tag else soup

        # 1. Inspect all <img> elements
        img_tags = scope.find_all("img")
        for idx, img in enumerate(img_tags, start=1):
            chosen_url = None
            resolved_url = None
            detected_attrs = {}

            # Gather attributes
            for attr in LAZY_ATTR_CANDIDATES:
                val = img.get(attr)
                if val and isinstance(val, str) and val.strip():
                    detected_attrs[attr] = val.strip()
                    if not chosen_url and not val.strip().startswith("data:image"):
                        # Pick first non-inline-data URL in priority order
                        if attr in ("srcset", "data-srcset"):
                            best = parse_srcset_best_url(val, base_url)
                            if best:
                                chosen_url = best
                        else:
                            chosen_url = val.strip()

            # If only inline data-src or regular src
            if not chosen_url and img.get("src"):
                chosen_url = img.get("src").strip()

            if not chosen_url or chosen_url.startswith("javascript:"):
                continue

            resolved_url = normalize_image_url(chosen_url, base_url)

            # Build DOM path
            path_parts = []
            curr = img
            while curr and curr.name != "[document]":
                c_name = curr.name
                c_class = ".".join(curr.get("class", []))
                if c_class:
                    c_name += f".{c_class}"
                path_parts.insert(0, c_name)
                curr = curr.parent
            dom_path = " > ".join(path_parts[-5:])  # Keep last 5 ancestors

            parent = img.parent
            parent_tag = parent.name if parent else None
            parent_classes = parent.get("class", []) if parent else []

            # Parse dimensional attributes if present
            w = None
            h = None
            try:
                if img.get("width"):
                    w = int(img.get("width"))
                if img.get("height"):
                    h = int(img.get("height"))
            except ValueError:
                pass

            cand = ImageCandidate(
                url=chosen_url,
                resolved_url=resolved_url,
                dom_order=idx,
                dom_path=dom_path,
                parent_tag=parent_tag,
                parent_classes=parent_classes,
                attributes=detected_attrs,
                rendered_width=w,
                rendered_height=h,
                alt_text=img.get("alt"),
                title=img.get("title"),
                nearby_text=parent.get_text(strip=True)[:100] if parent else None,
                source_strategies={"STATIC_DOM"},
            )
            candidates.append(cand)

        # 2. Inspect picture > source elements if not already collected
        picture_tags = scope.find_all("picture")
        for pic in picture_tags:
            sources = pic.find_all("source")
            for src_tag in sources:
                srcset = src_tag.get("srcset")
                if srcset:
                    best_url = parse_srcset_best_url(srcset, base_url)
                    if best_url:
                        cand = ImageCandidate(
                            url=srcset,
                            resolved_url=best_url,
                            dom_order=len(candidates) + 1,
                            dom_path=f"picture > source",
                            parent_tag="picture",
                            attributes={"srcset": srcset},
                            source_strategies={"STATIC_DOM"},
                        )
                        candidates.append(cand)

        return candidates
