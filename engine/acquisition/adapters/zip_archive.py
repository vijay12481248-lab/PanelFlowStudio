from pathlib import Path
import zipfile
import asyncio
from typing import Any
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

class ZipArchiveAdapter(BaseSourceAdapter):
    @property
    def adapter_id(self) -> str:
        return "zip_archive"

    @property
    def display_name(self) -> str:
        return "ZIP / CBZ Archive"

    def can_handle(self, source: str | Path | dict) -> bool:
        if isinstance(source, dict):
            source = source.get("path", "")
        p = Path(str(source).strip())
        if not p.is_file():
            return False
        if p.suffix.lower() in (".zip", ".cbz"):
            return True
        try:
            return zipfile.is_zipfile(p)
        except Exception:
            return False

    def _get_archive_image_entries(self, archive_path: Path) -> list[str]:
        with zipfile.ZipFile(archive_path, "r") as zf:
            entries = []
            for name in zf.namelist():
                # Filter out macOS artifacts, directory markers, and non-images
                if name.startswith("__MACOSX/") or name.endswith("/"):
                    continue
                ext = Path(name).suffix.lower()
                if ext in settings.allowed_image_extensions:
                    entries.append(name)
            entries.sort(key=natural_sort_key)
            return entries

    def inspect(self, source: str | Path | dict) -> SourceInspectionResult:
        if isinstance(source, dict):
            source = source.get("path", "")
        archive_path = Path(str(source).strip())
        if not archive_path.is_file():
            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=False,
                source_type=SourceType.ZIP_ARCHIVE,
                error=f"Archive file not found: {archive_path}",
            )

        try:
            entries = self._get_archive_image_entries(archive_path)
            title_suggestion = archive_path.stem

            chapter = ChapterInfo(
                id="chapter_1",
                title=title_suggestion,
                sequence=1,
                source_uri=str(archive_path.resolve()),
                page_count=len(entries),
            )

            metadata = SourceMetadata(
                title=title_suggestion,
                source_url=str(archive_path.resolve()),
                suggested_reading_direction="ltr",
            )

            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=True,
                source_type=SourceType.ZIP_ARCHIVE,
                title_suggestion=title_suggestion,
                metadata=metadata,
                chapters=[chapter],
                total_pages_detected=len(entries),
            )
        except zipfile.BadZipFile:
            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=False,
                source_type=SourceType.ZIP_ARCHIVE,
                error=f"File is not a valid zip archive: {archive_path}",
            )

    def get_metadata(self, source: str | Path | dict) -> SourceMetadata:
        return self.inspect(source).metadata

    def list_chapters(self, source: str | Path | dict) -> list[ChapterInfo]:
        return self.inspect(source).chapters

    def list_pages(self, chapter: ChapterInfo) -> list[PageCandidate]:
        archive_path = Path(chapter.source_uri)
        entries = self._get_archive_image_entries(archive_path)
        candidates = []
        for idx, entry_name in enumerate(entries, start=1):
            candidates.append(
                PageCandidate(
                    sequence=idx,
                    source_uri=f"zip://{archive_path.resolve().as_posix()}!/{entry_name}",
                    suggested_filename=Path(entry_name).name,
                    extra_metadata={
                        "archive_path": str(archive_path.resolve()),
                        "entry_name": entry_name,
                    },
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

        archive_str = page.extra_metadata.get("archive_path")
        entry_name = page.extra_metadata.get("entry_name")

        if not archive_str or not entry_name:
            if page.source_uri.startswith("zip://"):
                parts = page.source_uri[len("zip://"):].split("!/", 1)
                if len(parts) == 2:
                    archive_str, entry_name = parts

        if not archive_str or not entry_name:
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message="Invalid zip page URI format",
            )

        # Security check: prevent zip path traversal
        if ".." in entry_name or entry_name.startswith("/"):
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message="Path traversal in zip entry is forbidden",
            )

        archive_path = Path(archive_str)
        if not archive_path.is_file():
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message=f"Archive file not found: {archive_path}",
            )

        try:
            await asyncio.sleep(0)
            with zipfile.ZipFile(archive_path, "r") as zf:
                data = zf.read(entry_name)

            val_info = validate_image_bytes(data, entry_name)

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(data)

            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
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
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message=f"Validation error: {ve}",
            )
        except Exception as e:
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message=f"Extraction failed: {str(e)}",
            )
