from pathlib import Path
import shutil
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
    sanitize_filename,
)

class LocalFolderAdapter(BaseSourceAdapter):
    @property
    def adapter_id(self) -> str:
        return "local_folder"

    @property
    def display_name(self) -> str:
        return "Local Folder"

    def can_handle(self, source: str | Path | dict) -> bool:
        if isinstance(source, dict):
            source = source.get("path", "")
        p = Path(str(source).strip())
        return p.is_dir()

    def _get_image_paths(self, folder: Path) -> list[Path]:
        all_files = [p for p in folder.iterdir() if p.is_file()]
        image_files = [
            p for p in all_files
            if p.suffix.lower() in settings.allowed_image_extensions
        ]
        # Sort using natural sort key for deterministic ordering
        image_files.sort(key=lambda p: natural_sort_key(p.name))
        return image_files

    def inspect(self, source: str | Path | dict) -> SourceInspectionResult:
        if isinstance(source, dict):
            source = source.get("path", "")
        folder = Path(str(source).strip())
        if not folder.is_dir():
            return SourceInspectionResult(
                adapter_id=self.adapter_id,
                is_valid=False,
                source_type=SourceType.LOCAL_FOLDER,
                error=f"Directory does not exist: {folder}",
            )

        image_files = self._get_image_paths(folder)
        title_suggestion = folder.name

        chapter = ChapterInfo(
            id="chapter_1",
            title=title_suggestion,
            sequence=1,
            source_uri=str(folder.resolve()),
            page_count=len(image_files),
        )

        metadata = SourceMetadata(
            title=title_suggestion,
            source_url=str(folder.resolve()),
            suggested_reading_direction="ltr",
        )

        return SourceInspectionResult(
            adapter_id=self.adapter_id,
            is_valid=True,
            source_type=SourceType.LOCAL_FOLDER,
            title_suggestion=title_suggestion,
            metadata=metadata,
            chapters=[chapter],
            total_pages_detected=len(image_files),
        )

    def get_metadata(self, source: str | Path | dict) -> SourceMetadata:
        result = self.inspect(source)
        return result.metadata

    def list_chapters(self, source: str | Path | dict) -> list[ChapterInfo]:
        result = self.inspect(source)
        return result.chapters

    def list_pages(self, chapter: ChapterInfo) -> list[PageCandidate]:
        folder = Path(chapter.source_uri)
        image_files = self._get_image_paths(folder)
        candidates = []
        for idx, img_path in enumerate(image_files, start=1):
            candidates.append(
                PageCandidate(
                    sequence=idx,
                    source_uri=str(img_path.resolve()),
                    suggested_filename=img_path.name,
                    extra_metadata={"original_path": str(img_path)},
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

        src_path = Path(page.source_uri)
        if not src_path.is_file():
            return DownloadedPageResult(
                sequence=page.sequence,
                source_uri=page.source_uri,
                success=False,
                error_message=f"Source file not found: {src_path}",
            )

        try:
            # Yield control to event loop
            await asyncio.sleep(0)

            with open(src_path, "rb") as f:
                data = f.read()

            val_info = validate_image_bytes(data, src_path.name)

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
                error_message=f"Import failed: {str(e)}",
            )
