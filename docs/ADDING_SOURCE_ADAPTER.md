# Adding a Source Adapter in PanelFlow Studio

This guide explains how to author, register, and test a new `SourceAdapter` for PanelFlow Studio.

---

## 1. Safety and Content Guidelines

Source adapters must strictly adhere to the following principles:
- **Authorized and Legitimate Ingestion Only**: Designed solely for public domain archives, Creative Commons repositories, user-owned archives, or sources with explicit authorization and open terms of service.
- **No Anti-Circumvention**: Never implement bypasses for DRM, paywalls, CAPTCHA systems, login-gated restrictions, or anti-access controls.
- **Rate-Limiting & Politeness**: Respect `robots.txt`, maintain reasonable request delays, apply exponential backoff on retries, and set appropriate User-Agent headers.

---

## 2. The `SourceAdapter` Protocol

Every adapter inherits from `BaseSourceAdapter` (located in `engine/acquisition/adapters/base.py`):

```python
from pathlib import Path
from engine.acquisition.adapters.base import BaseSourceAdapter
from engine.acquisition.models import (
    SourceInspectionResult,
    SourceMetadata,
    ChapterInfo,
    PageCandidate,
    DownloadedPageResult,
)

class MyCustomSourceAdapter(BaseSourceAdapter):
    @property
    def adapter_id(self) -> str:
        return "my_custom_adapter"

    @property
    def display_name(self) -> str:
        return "My Custom Repository"

    def can_handle(self, source: str | Path | dict) -> bool:
        """Return True if this adapter recognizes the source format, schema, or URL domain."""
        ...

    def inspect(self, source: str | Path | dict) -> SourceInspectionResult:
        """Quickly check whether the source is reachable, valid, and reports expected schema."""
        ...

    def get_metadata(self, source: str | Path | dict) -> SourceMetadata:
        """Fetch publication title, author, description, and licensing terms."""
        ...

    def list_chapters(self, source: str | Path | dict) -> list[ChapterInfo]:
        """Return the list of available chapters or volumes."""
        ...

    def list_pages(self, chapter: ChapterInfo) -> list[PageCandidate]:
        """Return ordered list of page candidates with sequence numbers."""
        ...

    async def download_page(
        self,
        page: PageCandidate,
        target_path: Path,
        cancel_token: Any | None = None
    ) -> DownloadedPageResult:
        """Download or copy a single page file, perform image validation, and return result."""
        ...
```

---

## 3. Step-by-Step Implementation Guide

### Step 1: Create Adapter File
Create `panelflow/engine/acquisition/adapters/my_custom_adapter.py`.

### Step 2: Implement Natural Deterministic Ordering
Ensure discovered files or pages are ordered using natural sort (so `page_2` comes before `page_10`). Use `engine.acquisition.downloader.sorting.natural_sort_key`.

### Step 3: Validate Images
Never trust file extensions or HTTP 200 responses blindly. Ensure the downloaded file is verified with `validate_image_bytes()`:
- Verifies magic numbers (JPEG, PNG, WEBP).
- Validates raster decoding using Pillow (`Image.open`) or OpenCV (`cv2.imdecode`).
- Rejects HTML error pages (e.g. `<html><body>404 Not Found</body></html>`).

### Step 4: Register in `AdapterRegistry`
Add the new adapter to `engine/acquisition/adapters/registry.py`:

```python
from engine.acquisition.adapters.my_custom_adapter import MyCustomSourceAdapter

def get_default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(LocalFolderAdapter())
    registry.register(ZipArchiveAdapter())
    registry.register(GenericAuthorizedWebAdapter())
    registry.register(MyCustomSourceAdapter())
    return registry
```

---

## 4. Testing Your Adapter

Write unit and integration tests under `panelflow/tests/unit/test_my_custom_adapter.py`:

1. **`test_can_handle`**: Verifies URL patterns or path schemas correctly match.
2. **`test_deterministic_ordering`**: Verifies discovered pages sort `1, 2, ... 9, 10, 11`.
3. **`test_validation_rejection`**: Verifies HTML or corrupt binary responses raise `ImageValidationError`.
4. **`test_cancel_and_retry`**: Verifies partial downloads can be aborted and resumed idempotently.
