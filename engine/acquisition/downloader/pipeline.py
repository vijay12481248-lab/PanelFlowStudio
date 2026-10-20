import asyncio
import logging
from pathlib import Path
from typing import Callable, Any
from datetime import datetime, timezone
import json
import hashlib
import shutil
import uuid

from engine.config.settings import settings
from engine.acquisition.models import (
    PageCandidate,
    ChapterInfo,
    DownloadedPageResult,
    AcquisitionManifest,
    ManifestPage,
)
from engine.acquisition.adapters.base import BaseSourceAdapter
from engine.security.paths import ensure_contained_directory, open_contained_output, promote_contained_file, read_contained_bytes

logger = logging.getLogger(__name__)

class PipelineCancellationToken:
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class DownloadPipeline:
    def __init__(self, concurrency: int | None = None):
        self.concurrency = concurrency or settings.max_concurrent_downloads

    async def execute(
        self,
        project_id: str,
        workspace_path: Path,
        adapter: BaseSourceAdapter,
        candidates: list[PageCandidate],
        source_meta: dict,
        rights_meta: dict,
        chapter_meta: dict,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_token: PipelineCancellationToken | None = None,
        existing_manifest: AcquisitionManifest | None = None,
    ) -> tuple[list[DownloadedPageResult], AcquisitionManifest]:
        """
        Executes the acquisition pipeline:
        1. Prepares destination folder `workspace_path / 'source'`
        2. Limits concurrency using Semaphore
        3. Downloads and validates each page candidate
        4. Isolates individual page failures (Page 1 OK, Page 2 FAIL, Page 3 OK)
        5. Updates manifest JSON
        """
        if not workspace_path.exists():
            ensure_contained_directory(workspace_path.parent, workspace_path.name)
        source_dir = ensure_contained_directory(workspace_path, "source")
        lease_component = getattr(cancel_token, "lease_id", None) or uuid.uuid4().hex
        safe_lease_component = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(lease_component))
        ensure_contained_directory(workspace_path, ".acquisition-staging")
        staging_dir = ensure_contained_directory(workspace_path, Path(".acquisition-staging") / safe_lease_component)

        sem = asyncio.Semaphore(self.concurrency)
        total = len(candidates)
        completed_count = 0
        results: list[DownloadedPageResult] = []

        manifest_pages: dict[int, ManifestPage] = {}
        if existing_manifest:
            for mp in existing_manifest.pages:
                manifest_pages[mp.sequence] = mp

        async def worker(page: PageCandidate) -> DownloadedPageResult:
            nonlocal completed_count
            if cancel_token and cancel_token.is_cancelled:
                return DownloadedPageResult(
                    sequence=page.sequence,
                    source_uri=page.source_uri,
                    success=False,
                    error_message="Acquisition cancelled by user",
                )

            # Determine clean target filename
            ext = Path(page.suggested_filename or "").suffix.lower()
            if ext not in settings.allowed_image_extensions:
                ext = ".jpg"
            target_filename = f"page_{page.sequence:04d}{ext}"
            authoritative_path = source_dir / target_filename
            target_path = staging_dir / target_filename

            async with sem:
                if cancel_token and cancel_token.is_cancelled:
                    return DownloadedPageResult(
                        sequence=page.sequence,
                        source_uri=page.source_uri,
                        success=False,
                        error_message="Acquisition cancelled by user",
                    )

                cached = manifest_pages.get(page.sequence)
                cached_bytes = None
                if cached and cached.status == "READY" and cached.source_url == page.source_uri and cached.filename == target_filename:
                    try:
                        cached_bytes = read_contained_bytes(workspace_path, Path("source") / target_filename)
                    except (FileNotFoundError, ValueError, OSError):
                        cached_bytes = None
                if (cached_bytes is not None and len(cached_bytes) == cached.bytes
                        and hashlib.sha256(cached_bytes).hexdigest() == cached.sha256):
                    completed_count += 1
                    if progress_callback:
                        progress_callback(completed_count / max(1, total), f"Reused verified page {page.sequence}/{total}")
                    return DownloadedPageResult(
                        sequence=page.sequence, source_uri=page.source_uri, target_path=authoritative_path,
                        filename=cached.filename, content_type=cached.content_type,
                        width=cached.width, height=cached.height, byte_size=cached.bytes,
                        sha256=cached.sha256, success=True,
                    )

                # Check for simulated delay from candidate extra_metadata
                delay = 0.0
                extra = getattr(page, "extra_metadata", None) or getattr(page, "metadata", None) or {}
                if isinstance(extra, dict) and "delay_sec" in extra:
                    try:
                        delay = float(extra["delay_sec"])
                    except (ValueError, TypeError):
                        delay = 0.0

                if delay > 0:
                    for _ in range(max(1, int(delay * 20))):
                        if cancel_token and cancel_token.is_cancelled:
                            return DownloadedPageResult(
                                sequence=page.sequence,
                                source_uri=page.source_uri,
                                success=False,
                                error_message="Acquisition cancelled by user",
                            )
                        await asyncio.sleep(0.05)

                res = await adapter.download_page(page, target_path, cancel_token)
                if cancel_token and cancel_token.is_cancelled:
                    return DownloadedPageResult(
                        sequence=page.sequence,
                        source_uri=page.source_uri,
                        success=False,
                        error_message="Acquisition cancelled by user",
                    )
                completed_count += 1
                if progress_callback:
                    pct = completed_count / total if total > 0 else 1.0
                    msg = f"Processed page {completed_count}/{total} ({page.sequence})"
                    progress_callback(pct, msg)
                return res

        try:
            # External adapters write only into this lease-specific staging area.
            # They cannot be atomically revoked, so ownership is checked again
            # after they return and before every authoritative promotion.
            tasks = [worker(c) for c in candidates]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            results.sort(key=lambda r: r.sequence)

            if cancel_token and cancel_token.is_cancelled:
                raise RuntimeError("Acquisition worker lease was lost before publication")

            promoted_results: list[DownloadedPageResult] = []
            for result in results:
                if not result.success or not result.target_path:
                    promoted_results.append(result)
                    continue
                staged_path = Path(result.target_path)
                if staged_path.parent != staging_dir:
                    # Cache hits already reference the authoritative source file.
                    promoted_results.append(result)
                    continue
                if cancel_token and cancel_token.is_cancelled:
                    raise RuntimeError("Acquisition worker lease was lost before file promotion")
                authoritative_path = source_dir / result.filename
                promote_contained_file(workspace_path, staged_path.relative_to(workspace_path),
                                       authoritative_path.relative_to(workspace_path))
                promoted_results.append(result.model_copy(update={"target_path": authoritative_path}))
            results = promoted_results

            # Build manifest pages
            now_iso = datetime.now(timezone.utc).isoformat()

            updated_manifest_pages: list[ManifestPage] = []
            for r in results:
                # Check if we already had a stable ID from existing manifest
                existing_page = manifest_pages.get(r.sequence)
                page_id = existing_page.id if existing_page else str(uuid.uuid4())

                if r.success:
                    mp = ManifestPage(
                        id=page_id,
                        sequence=r.sequence,
                        filename=r.filename,
                        source_url=r.source_uri,
                        sha256=r.sha256,
                        width=r.width,
                        height=r.height,
                        bytes=r.byte_size,
                        content_type=r.content_type,
                        status="READY",
                        error_message=None,
                    )
                else:
                    mp = ManifestPage(
                        id=page_id,
                        sequence=r.sequence,
                        filename=r.filename or f"page_{r.sequence:04d}.jpg",
                        source_url=r.source_uri,
                        sha256="",
                        width=0,
                        height=0,
                        bytes=0,
                        content_type="unknown",
                        status="FAILED",
                        error_message=r.error_message,
                    )
                updated_manifest_pages.append(mp)

            manifest = AcquisitionManifest(
                project_id=project_id,
                version="1.0",
                created_at=existing_manifest.created_at if existing_manifest else now_iso,
                updated_at=now_iso,
                source=source_meta,
                rights=rights_meta,
                chapter=chapter_meta,
                pages=updated_manifest_pages,
            )

            if cancel_token and cancel_token.is_cancelled:
                raise RuntimeError("Acquisition worker lease was lost before manifest publication")
            with open_contained_output(workspace_path, "manifest.json") as manifest_output:
                if cancel_token and cancel_token.is_cancelled:
                    raise RuntimeError("Acquisition worker lease was lost before manifest promotion")
                manifest_output.write(manifest.model_dump_json(indent=2).encode("utf-8"))

            return results, manifest
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
