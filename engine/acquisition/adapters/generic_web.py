import asyncio
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup

from engine.config.settings import settings
from engine.acquisition.models import (
    SourceType,
    SourceInspectionResult,
    SourceMetadata,
    ChapterInfo,
    PageCandidate,
    DownloadedPageResult,
)
from engine.acquisition.adapters.base import BaseSourceAdapter
from engine.acquisition.downloader.sorting import natural_sort_key
from engine.acquisition.downloader.validation import (
    validate_image_bytes,
    ImageValidationError,
)

logger = logging.getLogger(__name__)

class GenericAuthorizedWebAdapter(BaseSourceAdapter):
    @property
    def adapter_id(self) -> str:
        return "generic_authorized_web"

    @property
    def display_name(self) -> str:
        return "Generic Authorized Web Source"

    def can_handle(self, source: str | Path | dict) -> bool:
        if isinstance(source, dict):
            url = source.get("url", "")
        else:
            url = str(source).strip()
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def _extract_url(self, source: str | Path | dict) -> str:
        if isinstance(source, dict):
            return source.get("url", "").strip()
        return str(source).strip()

    def inspect(self, source: str | Path | dict) -> SourceInspectionResult:
        url = self._extract_url(source)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=False,
                source_type=SourceType.AUTHORIZED_WEB,
                error=f"Invalid HTTP/HTTPS URL: {url}",
            )

        try:
            # Synchronous inspection with standard timeout and TLS verification
            with httpx.Client(
                timeout=settings.download_timeout_seconds,
                verify=True,
                follow_redirects=True,
                headers={"User-Agent": "PanelFlowStudio/0.1.0 (Authorized Ingestion Engine)"}
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()

            # Check if this is a direct single image URL
            if any(img_mime in content_type for img_mime in settings.allowed_mime_types):
                title_suggestion = Path(parsed.path).stem or "Web Image"
                chapter = ChapterInfo(
                    id="single_page",
                    title=title_suggestion,
                    sequence=1,
                    source_uri=url,
                    page_count=1,
                )
                return SourceInspectionResult(
                    adapter_id=self.adapter_id,
                    is_valid=True,
                    source_type=SourceType.AUTHORIZED_WEB,
                    title_suggestion=title_suggestion,
                    metadata=SourceMetadata(title=title_suggestion, source_url=url),
                    chapters=[chapter],
                    total_pages_detected=1,
                )

            # Check if JSON manifest
            if "application/json" in content_type:
                data = resp.json()
                title_suggestion = data.get("title", parsed.netloc)
                pages_data = data.get("pages", [])
                chapter = ChapterInfo(
                    id="manifest_chapter",
                    title=title_suggestion,
                    sequence=1,
                    source_uri=url,
                    page_count=len(pages_data),
                    extra_metadata={"manifest": data},
                )
                return SourceInspectionResult(
                    adapter_id=self.adapter_id,
                    is_valid=True,
                    source_type=SourceType.AUTHORIZED_WEB,
                    title_suggestion=title_suggestion,
                    metadata=SourceMetadata(
                        title=title_suggestion,
                        author=data.get("author"),
                        license_declared=data.get("license"),
                        source_url=url,
                    ),
                    chapters=[chapter],
                    total_pages_detected=len(pages_data),
                )

            # Standard HTML page parsing
            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            title_suggestion = title_tag.get_text(strip=True) if title_tag else parsed.netloc

            img_tags = soup.find_all("img")
            valid_srcs = []
            for img in img_tags:
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if not src:
                    continue
                full_url = urljoin(url, src)
                # Filter out trivial icons/logos if they don't match image extensions
                p_url = urlparse(full_url)
                ext = Path(p_url.path).suffix.lower()
                if ext in settings.allowed_image_extensions or "image" in src.lower() or "page" in src.lower():
                    valid_srcs.append(full_url)

            # Deduplicate while preserving discovered order
            seen = set()
            unique_srcs = []
            for s in valid_srcs:
                if s not in seen:
                    seen.add(s)
                    unique_srcs.append(s)

            chapter = ChapterInfo(
                id="web_chapter_1",
                title=title_suggestion,
                sequence=1,
                source_uri=url,
                page_count=len(unique_srcs),
                extra_metadata={"discovered_urls": unique_srcs},
            )

            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=True,
                source_type=SourceType.AUTHORIZED_WEB,
                title_suggestion=title_suggestion,
                metadata=SourceMetadata(
                    title=title_suggestion,
                    source_url=url,
                    suggested_reading_direction="ltr",
                ),
                chapters=[chapter],
                total_pages_detected=len(unique_srcs),
            )

        except Exception as e:
            logger.warning(f"Inspection error for {url}: {e}")
            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=False,
                source_type=SourceType.AUTHORIZED_WEB,
                error=f"Web inspection failed: {str(e)}",
            )

    def get_metadata(self, source: str | Path | dict) -> SourceMetadata:
        return self.inspect(source).metadata

    def list_chapters(self, source: str | Path | dict) -> list[ChapterInfo]:
        return self.inspect(source).chapters

    def list_pages(self, chapter: ChapterInfo) -> list[PageCandidate]:
        discovered = chapter.extra_metadata.get("discovered_urls", [])
        manifest = chapter.extra_metadata.get("manifest")

        candidates = []
        if manifest and "pages" in manifest:
            for idx, p_info in enumerate(manifest["pages"], start=1):
                p_url = p_info if isinstance(p_info, str) else p_info.get("url", "")
                candidates.append(
                    PageCandidate(
                        sequence=idx,
                        source_uri=p_url,
                        suggested_filename=f"page_{idx:04d}.jpg",
                        extra_metadata={"source_page_info": p_info},
                    )
                )
        elif discovered:
            for idx, p_url in enumerate(discovered, start=1):
                parsed = urlparse(p_url)
                clean_stem = Path(parsed.path).name or f"page_{idx:04d}.jpg"
                candidates.append(
                    PageCandidate(
                        sequence=idx,
                        source_uri=p_url,
                        suggested_filename=clean_stem,
                    )
                )
        else:
            # Direct single page
            candidates.append(
                PageCandidate(
                    sequence=1,
                    source_uri=chapter.source_uri,
                    suggested_filename=f"page_0001.jpg",
                )
            )

        return candidates

    async def download_page(
        self,
        page: PageCandidate,
        target_path: Path,
        cancel_token: Any | None = None,
    ) -> DownloadedPageResult:
        if cancel_token and getattr(cancel_token, "is_cancelled", False):
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message="Acquisition cancelled by user",
            )

        url = page.source_uri
        retries = settings.max_retries
        backoff = settings.retry_backoff_factor

        last_error = "Unknown error"
        for attempt in range(1, retries + 1):
            if cancel_token and getattr(cancel_token, "is_cancelled", False):
                return DownloadedPageResult(
                    sequence=page.sequence,
                    source_uri=page.source_uri,
                    success=False,
                    error_message="Acquisition cancelled by user",
                )

            try:
                # Rate limit courtesy delay
                if settings.rate_limit_delay_seconds > 0:
                    await asyncio.sleep(settings.rate_limit_delay_seconds)

                async with httpx.AsyncClient(
                    timeout=settings.download_timeout_seconds,
                    verify=True,
                    follow_redirects=True,
                    headers={"User-Agent": "PanelFlowStudio/0.1.0 (Authorized Ingestion Engine)"}
                ) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.content

                if len(data) > settings.max_download_bytes_per_file:
                    return DownloadedPageResult(
                        sequence=page.sequence,
                        source_uri=url,
                        success=False,
                        error_message=f"File exceeds maximum allowed size ({len(data)} > {settings.max_download_bytes_per_file})",
                    )

                # Validate image bytes (rejecting HTML error pages)
                val_info = validate_image_bytes(data, Path(urlparse(url).path).name)

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(data)

                return DownloadedPageResult(
                    sequence=page.sequence,
                    source_uri=url,
                    target_path=target_path,
                    filename=target_path.name,
                    content_type=val_info["mime_type"],
                    width=val_info["width"],
                    height=val_info["height"],
                    byte_size=val_info["byte_size"],
                    sha256=val_info["sha256"],
                    success=True,
                )

            except ImageValidationError as ve:
                # Validation error (e.g. HTML error page or corrupt bytes) is terminal for this attempt
                last_error = f"Image validation failed: {ve}"
                logger.warning(f"Download page {page.sequence} validation failed (attempt {attempt}/{retries}): {ve}")
            except httpx.HTTPStatusError as he:
                last_error = f"HTTP error {he.response.status_code}: {he.response.reason_phrase}"
                if he.response.status_code in (401, 403, 404):
                    # Client errors don't benefit from retries
                    break
            except Exception as e:
                last_error = f"Download network exception: {str(e)}"
                logger.warning(f"Download page {page.sequence} attempt {attempt}/{retries} error: {e}")

            if attempt < retries:
                await asyncio.sleep(backoff ** attempt)

        return DownloadedPageResult(
            sequence=page.sequence,
            source_uri=url,
            success=False,
            error_message=last_error,
        )
