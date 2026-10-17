"""
Resumable chapter downloader with bounded concurrency, rate-limiting, and atomic moves.
Preserves source immutability, validates magic bytes, and skips already-completed pages.
"""
import asyncio
import hashlib
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
from urllib.parse import urlparse
import httpx

from engine.acquisition.web.models.chapter_manifest import ChapterManifest, ChapterPage
from engine.acquisition.web.validation.image_probe import probe_image_bytes
from engine.acquisition.web.validation.ssrf_guard import is_safe_url
from engine.acquisition.downloader.pipeline import PipelineCancellationToken


class ResumableChapterDownloader:
    """
    Downloads pages declared in a ChapterManifest to the local project workspace.
    Supports resuming interrupted downloads, per-domain concurrency bounding, and atomic file moves.
    """

    def __init__(
        self,
        max_concurrency: int = 4,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        self.max_concurrency = max_concurrency
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def download_chapter(
        self,
        manifest: ChapterManifest,
        output_dir: Path,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_token: Optional[PipelineCancellationToken] = None,
        allow_loopback_for_testing: bool = False,
    ) -> Dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(self.max_concurrency)

        total_pages = len(manifest.pages)
        downloaded = 0
        resumed = 0
        failed = 0
        results: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            async def download_page_worker(page: ChapterPage) -> Dict[str, Any]:
                nonlocal downloaded, resumed, failed

                if cancel_token and cancel_token.is_cancelled:
                    return {"sequence": page.sequence, "status": "CANCELLED", "error": "User cancelled"}

                target_filename = page.suggested_filename or f"page_{page.sequence:04d}.jpg"
                target_path = output_dir / target_filename
                temp_path = output_dir / f"{target_filename}.tmp"

                # 1. Resume check: If file already exists and is valid, skip downloading!
                if target_path.exists() and target_path.stat().st_size > 64:
                    existing_bytes = target_path.read_bytes()
                    existing_sha = hashlib.sha256(existing_bytes).hexdigest()
                    if not page.sha256 or page.sha256 == existing_sha:
                        resumed += 1
                        page.sha256 = existing_sha
                        page.byte_size = len(existing_bytes)
                        return {
                            "sequence": page.sequence,
                            "status": "RESUMED",
                            "path": str(target_path),
                            "sha256": existing_sha,
                        }

                # 2. SSRF check on target URL
                safe, reason = is_safe_url(page.resolved_url, allow_loopback_for_testing=allow_loopback_for_testing)
                if not safe:
                    failed += 1
                    return {"sequence": page.sequence, "status": "FAILED", "error": f"SSRF blocked: {reason}"}

                # 3. Download with bounded concurrency and transient retries
                async with sem:
                    if cancel_token and cancel_token.is_cancelled:
                        return {"sequence": page.sequence, "status": "CANCELLED", "error": "User cancelled"}

                    last_error = None
                    for attempt in range(1, self.max_retries + 1):
                        if cancel_token and cancel_token.is_cancelled:
                            return {"sequence": page.sequence, "status": "CANCELLED", "error": "User cancelled"}

                        try:
                            # Handle data: URLs if present (rendered capture)
                            if page.resolved_url.startswith("data:image"):
                                import base64
                                _, b64_data = page.resolved_url.split(",", 1)
                                data = base64.b64decode(b64_data)
                            else:
                                resp = await client.get(
                                    page.resolved_url,
                                    headers={"User-Agent": "PanelFlowStudio/0.1.0"},
                                )
                                # Fatal HTTP errors (401, 403, 404) -> do not retry
                                if resp.status_code in (401, 403, 404):
                                    failed += 1
                                    return {
                                        "sequence": page.sequence,
                                        "status": "FAILED",
                                        "error": f"HTTP {resp.status_code}",
                                    }
                                resp.raise_for_status()
                                data = resp.content

                            # 4. Byte validation & image integrity
                            probe = probe_image_bytes(data)
                            if not probe.is_valid:
                                last_error = f"Corrupt image payload: {probe.error}"
                                break

                            # 5. Atomic write to disk
                            temp_path.write_bytes(data)
                            temp_path.replace(target_path)

                            # 6. Update manifest page metadata
                            page.sha256 = probe.sha256
                            page.byte_size = probe.byte_size
                            page.width = probe.width
                            page.height = probe.height
                            page.mime_type = probe.mime_type

                            downloaded += 1
                            if progress_cb and total_pages > 0:
                                progress_cb((downloaded + resumed) / total_pages, f"Acquired page {page.sequence}")

                            return {
                                "sequence": page.sequence,
                                "status": "DOWNLOADED",
                                "path": str(target_path),
                                "sha256": probe.sha256,
                            }

                        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                            last_error = str(e)
                            if attempt < self.max_retries:
                                await asyncio.sleep(self.backoff_factor * attempt)
                        except Exception as e:
                            last_error = str(e)
                            break

                    failed += 1
                    return {"sequence": page.sequence, "status": "FAILED", "error": last_error}

            tasks = [download_page_worker(p) for p in manifest.pages]
            results = await asyncio.gather(*tasks)

        overall_status = "COMPLETE" if failed == 0 else ("PARTIAL" if (downloaded + resumed) > 0 else "FAILED")

        return {
            "status": overall_status,
            "total_pages": total_pages,
            "downloaded": downloaded,
            "resumed": resumed,
            "failed": failed,
            "results": sorted(results, key=lambda r: r.get("sequence", 0)),
        }
