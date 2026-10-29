"""
Smart Manga Series & Chapter Discovery Engine.
Implements Strategy and Chain-of-Responsibility patterns to automatically discover,
extract, and sequence all chapters/episodes from series pages, reader dropdowns,
breadcrumbs, and URL patterns.
"""
import re
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup

from engine.acquisition.web.series.models import SeriesChapter, SeriesMetadata
from engine.acquisition.web.validation.ssrf_guard import is_safe_url

logger = logging.getLogger("panelflow.series.discovery")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Regex for parsing chapter numbers from text or URL slugs
CHAPTER_NUM_REGEX = re.compile(
    r"(?:chapter|ch\.?|episode|ep\.?|#)\s*[-_]?\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
CHAPTER_URL_NUM_REGEX = re.compile(
    r"[-_/](?:chapter|ch|ep|episode)[-_/]?([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
SERIES_PATH_REGEX = re.compile(
    r"^(.*?/(?:manga|series|comic|comics|webcomics|title|detail)/[^/]+)/?",
    re.IGNORECASE,
)


def parse_chapter_number(text: str, url: str) -> Optional[float]:
    """
    Extracts a numeric chapter sequence from display text or URL.
    Handles floats like 921.5, integers like 927, and leading zeroes.
    """
    if text:
        match = CHAPTER_NUM_REGEX.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    if url:
        match = CHAPTER_URL_NUM_REGEX.search(url)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        # Fallback: check trailing digit slug
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts:
            last = parts[-1]
            num_match = re.search(r"(\d+(?:\.\d+)?)", last)
            if num_match:
                try:
                    return float(num_match.group(1))
                except ValueError:
                    pass

    return None


def infer_series_url_and_pattern(chapter_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Given a single chapter URL, infers the parent series URL and template pattern.
    Example:
      Input:  https://manhuaplus.com/manga/demon-magic-emperor01/chapter-927/
      Series: https://manhuaplus.com/manga/demon-magic-emperor01/
      Pattern: https://manhuaplus.com/manga/demon-magic-emperor01/chapter-{chapter_number}/
    """
    parsed = urlparse(chapter_url)
    m = SERIES_PATH_REGEX.match(parsed.path)
    if m:
        series_path = m.group(1).rstrip("/") + "/"
        series_url = f"{parsed.scheme}://{parsed.netloc}{series_path}"
        # Build pattern template by replacing chapter number
        num_match = CHAPTER_URL_NUM_REGEX.search(parsed.path)
        if num_match:
            full_match = num_match.group(0)
            pattern_path = parsed.path.replace(num_match.group(1), "{chapter_number}")
            pattern_url = f"{parsed.scheme}://{parsed.netloc}{pattern_path}"
            return series_url, pattern_url
        return series_url, None

    # Fallback: strip last path component
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        parent_path = "/" + "/".join(parts[:-1]) + "/"
        series_url = f"{parsed.scheme}://{parsed.netloc}{parent_path}"
        return series_url, None

    return None, None


class BaseSeriesDiscoveryStrategy(ABC):
    """
    Abstract Strategy for discovering chapters from a manga source.
    """

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        pass

    @abstractmethod
    async def can_handle(self, url: str, html_text: Optional[str] = None) -> bool:
        pass

    @abstractmethod
    async def discover(
        self,
        url: str,
        html_text: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[SeriesMetadata]:
        pass


class ChapterDropdownStrategy(BaseSeriesDiscoveryStrategy):
    """
    Extracts all chapters directly from a reader page chapter dropdown (<select>).
    Widely present on Madara, MangaReader, and modern webtoon readers.
    """

    @property
    def strategy_name(self) -> str:
        return "CHAPTER_DROPDOWN"

    async def can_handle(self, url: str, html_text: Optional[str] = None) -> bool:
        if not html_text:
            return False
        soup = BeautifulSoup(html_text, "html.parser")
        return bool(soup.select("select.single-chapter-select, select.selectpicker_chapter, select#chapter, select#single-pager"))

    async def discover(
        self,
        url: str,
        html_text: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[SeriesMetadata]:
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        select_el = soup.select_one("select.single-chapter-select, select.selectpicker_chapter, select#chapter, select#single-pager")
        if not select_el:
            # Fallback: find any select with option tags mentioning chapter
            for s in soup.find_all("select"):
                ops = s.find_all("option")
                if len(ops) > 3 and any("chapter" in o.get_text().lower() for o in ops[:5]):
                    select_el = s
                    break

        if not select_el:
            return None

        options = select_el.find_all("option")
        if not options:
            return None

        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        title_tag = soup.find("title")
        series_title = title_tag.get_text(strip=True).split("-")[0].strip() if title_tag else domain

        # Deduce series URL
        series_url, pattern = infer_series_url_and_pattern(url)
        if not series_url:
            series_url = url

        chapters_map: Dict[float, SeriesChapter] = {}
        for opt in options:
            opt_text = opt.get_text(strip=True)
            opt_val = opt.get("value", "").strip()
            # If value is URL or relative path
            chap_url = urljoin(url, opt_val) if opt_val else ""
            if not chap_url or not chap_url.startswith("http"):
                # Check data-redirect or data-url attributes
                chap_url = opt.get("data-redirect") or opt.get("data-url") or ""
                if chap_url:
                    chap_url = urljoin(url, chap_url)

            if not chap_url:
                continue

            seq = parse_chapter_number(opt_text, chap_url)
            if seq is not None and seq not in chapters_map:
                chapters_map[seq] = SeriesChapter(
                    sequence=seq,
                    title=opt_text or f"Chapter {seq:g}",
                    url=chap_url,
                )

        if not chapters_map:
            return None

        sorted_chapters = sorted(chapters_map.values(), key=lambda c: c.sequence)
        min_seq = sorted_chapters[0].sequence
        max_seq = sorted_chapters[-1].sequence

        return SeriesMetadata(
            title=series_title,
            series_url=series_url,
            source_domain=domain,
            total_chapters_detected=len(sorted_chapters),
            chapters=sorted_chapters,
            url_pattern=pattern,
            detected_range=(min_seq, max_seq),
            discovery_strategy=self.strategy_name,
            diagnostics={"extracted_from_select_options": len(options)},
        )


class SeriesTocStrategy(BaseSeriesDiscoveryStrategy):
    """
    Extracts all chapters from the main Series Table of Contents page.
    Handles Madara themes (.wp-manga-chapter), MangaReader (.chapter-list, #chapterlist),
    and general DOM chapter listings.
    """

    @property
    def strategy_name(self) -> str:
        return "SERIES_TOC"

    async def can_handle(self, url: str, html_text: Optional[str] = None) -> bool:
        if html_text:
            soup = BeautifulSoup(html_text, "html.parser")
            return bool(soup.select(".wp-manga-chapter, #chapterlist, .listing-chapters_wrap, .chapter-list, .chapters, ul.version-chap"))
        return "/manga/" in url.lower() or "/series/" in url.lower()

    async def discover(
        self,
        url: str,
        html_text: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[SeriesMetadata]:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        # If html_text is not provided, fetch it
        if html_text is None:
            own_client = False
            if client is None:
                client = httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=DEFAULT_HEADERS)
                own_client = True
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                html_text = resp.text
            finally:
                if own_client:
                    await client.aclose()

        soup = BeautifulSoup(html_text, "html.parser")

        # Extract series title
        title_el = (
            soup.select_one(".post-title h1, .manga-title, .series-title, h1.entry-title")
            or soup.find("h1")
            or soup.find("title")
        )
        series_title = title_el.get_text(strip=True) if title_el else domain
        # Clean title suffix (e.g. "Magic Emperor - ManhuaPlus" -> "Magic Emperor")
        for separator in ("-", "|", "–", "»"):
            if separator in series_title:
                parts = series_title.split(separator)
                if len(parts[0].strip()) > 3:
                    series_title = parts[0].strip()
                    break

        # Extract cover image
        cover_el = soup.select_one(".summary_image img, .manga-poster img, .series-thumb img, .thumb img")
        cover_url = cover_el.get("src") or cover_el.get("data-src") if cover_el else None
        if cover_url:
            cover_url = urljoin(url, cover_url)

        # Extract description
        desc_el = soup.select_one(".summary__content, .manga-summary, .series-synopsis, .description-summary")
        description = desc_el.get_text(strip=True) if desc_el else None

        # Determine the series slug to filter out related manga links
        series_slug = parsed_url.path.strip("/").split("/")[-1]

        # Collect candidate chapter links
        # Priority containers
        container = soup.select_one(
            ".listing-chapters_wrap, #chapterlist, .chapter-list, .chapters, ul.version-chap, .main.version-chap, .wp-manga-chapter"
        )
        scope = container if container else soup

        raw_links = scope.find_all("a", href=True)
        chapters_map: Dict[float, SeriesChapter] = {}

        for a in raw_links:
            href = a.get("href", "").strip()
            full_url = urljoin(url, href)
            # Ensure it is a valid HTTP URL and from the same domain
            p_link = urlparse(full_url)
            if p_link.netloc.lower() != domain:
                continue

            # Exclude non-chapter pages (e.g. bookmark, first, last, login, comment)
            link_text = a.get_text(strip=True)
            if any(k in link_text.lower() for k in ("read first", "read last", "bookmark", "login", "discord")):
                continue

            # Must contain chapter indicator in href or text
            if not (CHAPTER_URL_NUM_REGEX.search(p_link.path) or "chapter" in link_text.lower() or "ch." in link_text.lower()):
                continue

            # Series slug affinity check: prevent related manga links
            if series_slug and series_slug not in p_link.path:
                continue

            seq = parse_chapter_number(link_text, full_url)
            if seq is not None and seq not in chapters_map:
                # Find optional date released nearby
                parent_li = a.find_parent(["li", "tr", "div"])
                date_str = None
                if parent_li:
                    date_el = parent_li.select_one(".chapter-release-date, .release-date, .date, span")
                    if date_el and date_el != a:
                        date_str = date_el.get_text(strip=True)

                chapters_map[seq] = SeriesChapter(
                    sequence=seq,
                    title=link_text or f"Chapter {seq:g}",
                    url=full_url,
                    date_released=date_str,
                )

        if not chapters_map:
            return None

        sorted_chapters = sorted(chapters_map.values(), key=lambda c: c.sequence)
        min_seq = sorted_chapters[0].sequence
        max_seq = sorted_chapters[-1].sequence

        # Infer URL pattern template
        pattern = None
        if sorted_chapters:
            sample_url = sorted_chapters[-1].url
            _, pattern = infer_series_url_and_pattern(sample_url)

        return SeriesMetadata(
            title=series_title,
            series_url=url,
            source_domain=domain,
            cover_image_url=cover_url,
            description=description,
            total_chapters_detected=len(sorted_chapters),
            chapters=sorted_chapters,
            url_pattern=pattern,
            detected_range=(min_seq, max_seq),
            discovery_strategy=self.strategy_name,
            diagnostics={"unique_chapters_parsed": len(sorted_chapters)},
        )


class BreadcrumbSeriesStrategy(BaseSeriesDiscoveryStrategy):
    """
    When given a single chapter URL, locates the parent series URL via breadcrumbs
    or navigation, fetches the series page, and delegates to SeriesTocStrategy.
    """

    def __init__(self, toc_strategy: Optional[SeriesTocStrategy] = None):
        self.toc_strategy = toc_strategy or SeriesTocStrategy()

    @property
    def strategy_name(self) -> str:
        return "BREADCRUMB_SERIES_TOC"

    async def can_handle(self, url: str, html_text: Optional[str] = None) -> bool:
        if html_text:
            soup = BeautifulSoup(html_text, "html.parser")
            return bool(soup.select(".breadcrumb a, .breadcrumbs a, .c-breadcrumb a"))
        return False

    async def discover(
        self,
        url: str,
        html_text: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[SeriesMetadata]:
        if not html_text:
            return None

        soup = BeautifulSoup(html_text, "html.parser")
        breadcrumb_links = soup.select(".breadcrumb a, .breadcrumbs a, .c-breadcrumb a")
        parent_url = None
        for a in reversed(breadcrumb_links):
            href = a.get("href", "").strip()
            full_url = urljoin(url, href)
            # Find link that points to a series/manga page (not the root homepage and not current chapter)
            parsed = urlparse(full_url)
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) >= 2 and not CHAPTER_URL_NUM_REGEX.search(parsed.path):
                parent_url = full_url
                break

        if not parent_url:
            return None

        logger.info(f"Breadcrumb strategy discovered series page: {parent_url}")
        meta = await self.toc_strategy.discover(parent_url, client=client)
        if meta:
            meta.discovery_strategy = self.strategy_name
        return meta


class UrlPatternProbeStrategy(BaseSeriesDiscoveryStrategy):
    """
    Deconstructs chapter URL numbering pattern and provides sequential probing
    or range expansion for sites with protected or dynamically loaded TOCs.
    """

    @property
    def strategy_name(self) -> str:
        return "URL_PATTERN_PROBE"

    async def can_handle(self, url: str, html_text: Optional[str] = None) -> bool:
        return bool(CHAPTER_URL_NUM_REGEX.search(url))

    async def discover(
        self,
        url: str,
        html_text: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[SeriesMetadata]:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        current_seq = parse_chapter_number("", url)
        if current_seq is None:
            return None

        series_url, pattern = infer_series_url_and_pattern(url)
        if not pattern:
            return None

        series_title = "Manga Series"
        if html_text:
            soup = BeautifulSoup(html_text, "html.parser")
            title_tag = soup.find("title")
            if title_tag:
                series_title = title_tag.get_text(strip=True).split("-")[0].strip()

        # Seed with the known chapter
        seed_chapter = SeriesChapter(
            sequence=current_seq,
            title=f"Chapter {current_seq:g}",
            url=url,
        )

        return SeriesMetadata(
            title=series_title,
            series_url=series_url or url,
            source_domain=domain,
            total_chapters_detected=1,
            chapters=[seed_chapter],
            url_pattern=pattern,
            detected_range=(current_seq, current_seq),
            discovery_strategy=self.strategy_name,
            diagnostics={"pattern_template": pattern, "seed_chapter": current_seq},
        )

    @staticmethod
    def generate_range_chapters(pattern_url: str, start: float, end: float, step: float = 1.0) -> List[SeriesChapter]:
        """
        Generates a sequence of SeriesChapter objects by expanding the URL pattern template.
        Supports integer and float chapter ranges.
        """
        chapters = []
        curr = start
        while curr <= end + 1e-6:
            # Format as integer if whole number
            num_str = f"{int(curr)}" if curr.is_integer() else f"{curr:g}"
            chap_url = pattern_url.replace("{chapter_number}", num_str)
            chapters.append(
                SeriesChapter(
                    sequence=curr,
                    title=f"Chapter {num_str}",
                    url=chap_url,
                )
            )
            curr += step
        return chapters


class SmartSeriesDiscoveryEngine:
    """
    Composite Orchestrator coordinating all discovery strategies.
    Accepts any manga URL (series index or individual chapter) and returns
    a fully resolved, deduplicated, naturally sorted SeriesMetadata catalog.
    """

    def __init__(self):
        self.toc_strategy = SeriesTocStrategy()
        self.dropdown_strategy = ChapterDropdownStrategy()
        self.breadcrumb_strategy = BreadcrumbSeriesStrategy(toc_strategy=self.toc_strategy)
        self.pattern_strategy = UrlPatternProbeStrategy()

    async def discover_series(
        self,
        url: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SeriesMetadata:
        """
        Executes multi-strategy discovery to resolve all chapters for the target manga.
        """
        context = context or {}
        allow_loopback = context.get("allow_loopback_for_testing", False)

        safe, reason = is_safe_url(url, allow_loopback_for_testing=allow_loopback)
        if not safe:
            raise ValueError(f"SSRF safety check failed: {reason}")

        html_text = context.get("mock_html")

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            if html_text is None:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    raise ValueError(f"Failed to fetch manga page ({resp.status_code}): {resp.reason_phrase}")
                html_text = resp.text

            # 1. Try Chapter Reader Dropdown (if on a chapter reader page, this has all chapters in 1 request)
            if await self.dropdown_strategy.can_handle(url, html_text):
                res = await self.dropdown_strategy.discover(url, html_text, client=client)
                if res and res.total_chapters_detected >= 2:
                    logger.info(f"Discovered {res.total_chapters_detected} chapters via reader dropdown.")
                    return res

            # 2. Try Series TOC (if on series index page)
            if await self.toc_strategy.can_handle(url, html_text):
                res = await self.toc_strategy.discover(url, html_text, client=client)
                if res and res.total_chapters_detected >= 1:
                    logger.info(f"Discovered {res.total_chapters_detected} chapters via series TOC.")
                    return res

            # 3. Try Breadcrumbs to locate parent series TOC
            if await self.breadcrumb_strategy.can_handle(url, html_text):
                res = await self.breadcrumb_strategy.discover(url, html_text, client=client)
                if res and res.total_chapters_detected >= 1:
                    logger.info(f"Discovered {res.total_chapters_detected} chapters via breadcrumb series TOC.")
                    return res

            # 4. Try deducing parent series URL from URL path and fetching it
            series_url, pattern = infer_series_url_and_pattern(url)
            if series_url and series_url != url:
                logger.info(f"Inferred series URL {series_url} from chapter URL. Fetching series page...")
                try:
                    s_resp = await client.get(series_url)
                    if s_resp.status_code == 200:
                        res = await self.toc_strategy.discover(series_url, s_resp.text, client=client)
                        if res and res.total_chapters_detected >= 1:
                            if pattern and not res.url_pattern:
                                res.url_pattern = pattern
                            return res
                except Exception as e:
                    logger.warning(f"Failed fetching inferred series URL {series_url}: {e}")

            # 5. Fallback: URL Pattern Probe Strategy
            res = await self.pattern_strategy.discover(url, html_text, client=client)
            if res:
                return res

            raise ValueError(f"Unable to discover chapters from URL: {url}")
