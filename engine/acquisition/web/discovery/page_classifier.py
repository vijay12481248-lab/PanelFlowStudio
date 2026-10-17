"""
URL and HTML document classifier for web acquisition.
Determines if an input URL/document is a direct image, chapter reader, series index, archive, or non-content.
"""
import re
from urllib.parse import urlparse
from typing import Tuple, Optional
from bs4 import BeautifulSoup
from engine.acquisition.web.models.chapter_manifest import PageType

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}
ARCHIVE_EXTENSIONS = {".zip", ".cbz", ".cbr", ".rar", ".7z", ".tar", ".gz"}
DOCUMENT_EXTENSIONS = {".pdf", ".epub"}

CHAPTER_URL_REGEX = re.compile(
    r"(/chapter[-_/]?\d+|/ch[-_/]?\d+|/ep[-_/]?\d+|/episode[-_/]?\d+|/read/|/viewer/|chapter=\d+|ep=\d+)",
    re.IGNORECASE,
)
SERIES_URL_REGEX = re.compile(
    r"(/series/|/manga/|/comic/|/comics/|/webcomics/|/title/|/detail/|/info/)",
    re.IGNORECASE,
)
LOGIN_URL_REGEX = re.compile(
    r"(/login|/signin|/auth|/register|/signup|/account)",
    re.IGNORECASE,
)


class PageClassifier:
    """
    Classifies page type from URL and optional HTML response text.
    """

    def classify_url(self, url: str) -> PageType:
        parsed = urlparse(url.strip())
        path_lower = parsed.path.lower()

        # Direct image
        for ext in IMAGE_EXTENSIONS:
            if path_lower.endswith(ext):
                return PageType.DIRECT_IMAGE

        # Archive
        for ext in ARCHIVE_EXTENSIONS:
            if path_lower.endswith(ext):
                return PageType.ARCHIVE

        # Document
        for ext in DOCUMENT_EXTENSIONS:
            if path_lower.endswith(ext):
                return PageType.DOCUMENT

        # URL path keywords
        if LOGIN_URL_REGEX.search(path_lower):
            return PageType.NOT_CONTENT

        if CHAPTER_URL_REGEX.search(path_lower):
            return PageType.CHAPTER_PAGE

        if SERIES_URL_REGEX.search(path_lower) and not CHAPTER_URL_REGEX.search(path_lower):
            return PageType.SERIES_PAGE

        return PageType.UNKNOWN_PAGE

    def classify_document(
        self,
        url: str,
        html_text: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Tuple[PageType, float, str]:
        """
        Classifies page type with confidence and reasoning using URL and HTML content evidence.
        Returns (PageType, confidence, reason).
        """
        # 1. Direct Content-Type check
        if content_type:
            ct = content_type.lower()
            if any(img_mime in ct for img_mime in ("image/jpeg", "image/png", "image/webp", "image/avif")):
                return PageType.DIRECT_IMAGE, 1.0, f"Direct image Content-Type '{ct}'"
            if "application/pdf" in ct:
                return PageType.DOCUMENT, 1.0, "Direct PDF Content-Type"
            if any(arch_mime in ct for arch_mime in ("application/zip", "application/x-cbz", "application/x-cbr")):
                return PageType.ARCHIVE, 1.0, "Archive Content-Type"
            if "application/json" in ct or "text/json" in ct:
                return PageType.CHAPTER_PAGE, 0.95, "Direct JSON chapter manifest"

        url_type = self.classify_url(url)
        if url_type in (PageType.DIRECT_IMAGE, PageType.ARCHIVE, PageType.DOCUMENT):
            return url_type, 0.95, f"Direct resource URL path extension"

        if not html_text:
            return url_type, 0.60, "Classified solely by URL pattern"

        soup = BeautifulSoup(html_text, "html.parser")

        # 2. Check for login / restriction forms
        login_forms = soup.find_all("form", attrs={"action": LOGIN_URL_REGEX})
        password_inputs = soup.find_all("input", attrs={"type": "password"})
        title_text = soup.find("title").get_text(strip=True).lower() if soup.find("title") else ""

        if password_inputs or "login" in title_text or "sign in" in title_text:
            if not soup.find_all("img"):
                return PageType.NOT_CONTENT, 0.90, "Authentication/Login page detected"

        # 3. Reader container & image presence
        images = soup.find_all("img")
        img_count = len(images)

        # Check for chapter title indicators in headings
        headings = [h.get_text(strip=True).lower() for h in soup.find_all(["h1", "h2", "h3"])]
        chapter_heading = any("chapter" in h or "episode" in h or "ch." in h for h in headings)

        # Check for series chapter list / table of contents
        chapter_links = soup.find_all("a", href=CHAPTER_URL_REGEX)
        link_count = len(chapter_links)

        # If many chapter links -> likely a Series Page
        if link_count >= 5 and (img_count < 10 or link_count >= img_count * 0.5 or SERIES_URL_REGEX.search(url)):
            return PageType.SERIES_PAGE, 0.90, f"Series index with {link_count} chapter links"

        # If many images or chapter heading present -> likely a Chapter Page
        if img_count >= 3 or (chapter_heading and img_count >= 1):
            conf = 0.90 if chapter_heading and img_count >= 5 else 0.75
            return PageType.CHAPTER_PAGE, conf, f"Chapter page with {img_count} images and chapter indicators"

        if url_type == PageType.CHAPTER_PAGE:
            return PageType.CHAPTER_PAGE, 0.70, "URL indicates chapter despite low static image count"

        if img_count == 0 and not chapter_heading:
            return PageType.NOT_CONTENT, 0.85, "Non-reader web page (no images or chapter indicators)"

        return PageType.UNKNOWN_PAGE, 0.50, "Insufficient signals to unambiguously classify page"
