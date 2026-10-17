from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from engine.acquisition.models import (
    SourceInspectionResult,
    SourceMetadata,
    ChapterInfo,
    PageCandidate,
    DownloadedPageResult,
)

class BaseSourceAdapter(ABC):
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique machine identifier for this adapter (e.g., 'local_folder', 'zip_archive')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name for this adapter."""
        pass

    @abstractmethod
    def can_handle(self, source: str | Path | dict) -> bool:
        """Determines whether this adapter can process the given source."""
        pass

    @abstractmethod
    def inspect(self, source: str | Path | dict) -> SourceInspectionResult:
        """Quickly inspects the source, returning structure, chapter list, and detected page counts."""
        pass

    @abstractmethod
    def get_metadata(self, source: str | Path | dict) -> SourceMetadata:
        """Extracts title, creator, licensing notices, and reading direction."""
        pass

    @abstractmethod
    def list_chapters(self, source: str | Path | dict) -> list[ChapterInfo]:
        """Lists all chapters or sub-volumes available in this source."""
        pass

    @abstractmethod
    def list_pages(self, chapter: ChapterInfo) -> list[PageCandidate]:
        """Lists all page candidates for a given chapter in deterministic sequence order."""
        pass

    @abstractmethod
    async def download_page(
        self,
        page: PageCandidate,
        target_path: Path,
        cancel_token: Any | None = None,
    ) -> DownloadedPageResult:
        """
        Downloads or copies a single page candidate to target_path with integrity validation.
        Must check cancel_token if provided.
        """
        pass
