"""
Tests for resumable chapter downloader, atomic moves, and partial failure recovery.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.acquisition.web.downloader import ResumableChapterDownloader
from engine.acquisition.web.models.chapter_manifest import ChapterManifest, ChapterPage, SourceQuality
from tests.fixtures.helpers import create_test_image_bytes


@pytest.mark.asyncio
async def test_resumable_downloader_skips_existing_pages(tmp_path: Path):
    downloader = ResumableChapterDownloader(max_concurrency=2)
    output_dir = tmp_path / "chapter_source"
    output_dir.mkdir()

    img_data_1 = create_test_image_bytes(100, 100, "red")
    img_data_2 = create_test_image_bytes(100, 100, "green")

    # Pre-populate page 1 on disk as if already acquired
    import hashlib
    p1_sha = hashlib.sha256(img_data_1).hexdigest()
    (output_dir / "page_0001.jpg").write_bytes(img_data_1)

    manifest = ChapterManifest(
        source_url="https://example.com/ch1",
        canonical_url="https://example.com/ch1",
        domain="example.com",
        extraction_strategy="STATIC_DOM",
        extraction_confidence=0.95,
        completeness_score=1.0,
        pages=[
            ChapterPage(
                sequence=1,
                source_url="https://example.com/p1.jpg",
                resolved_url="https://example.com/p1.jpg",
                source_strategy="STATIC_DOM",
                suggested_filename="page_0001.jpg",
                sha256=p1_sha,
            ),
            ChapterPage(
                sequence=2,
                source_url="https://example.com/p2.jpg",
                resolved_url="https://example.com/p2.jpg",
                source_strategy="STATIC_DOM",
                suggested_filename="page_0002.jpg",
            ),
        ],
    )

    with patch("httpx.AsyncClient.get") as mock_get:
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.content = img_data_2
        resp2.raise_for_status = MagicMock()
        mock_get.return_value = resp2

        dl_res = await downloader.download_chapter(manifest, output_dir)

        assert dl_res["status"] == "COMPLETE"
        assert dl_res["resumed"] == 1  # Page 1 was skipped
        assert dl_res["downloaded"] == 1  # Only page 2 was downloaded
        assert dl_res["failed"] == 0

        # Check mock_get was only called once (for page 2, not page 1)
        assert mock_get.call_count == 1
        assert (output_dir / "page_0002.jpg").exists()


@pytest.mark.asyncio
async def test_resumable_downloader_partial_failure_and_resume(tmp_path: Path):
    downloader = ResumableChapterDownloader(max_concurrency=2, max_retries=1)
    output_dir = tmp_path / "chapter_partial"
    output_dir.mkdir()

    img_data_1 = create_test_image_bytes(100, 100, "red")
    img_data_2 = create_test_image_bytes(100, 100, "green")

    manifest = ChapterManifest(
        source_url="https://example.com/ch1",
        canonical_url="https://example.com/ch1",
        domain="example.com",
        extraction_strategy="STATIC_DOM",
        extraction_confidence=0.95,
        completeness_score=1.0,
        pages=[
            ChapterPage(
                sequence=1,
                source_url="https://example.com/p1.jpg",
                resolved_url="https://example.com/p1.jpg",
                source_strategy="STATIC_DOM",
                suggested_filename="page_0001.jpg",
            ),
            ChapterPage(
                sequence=2,
                source_url="https://example.com/p2.jpg",
                resolved_url="https://example.com/p2.jpg",
                source_strategy="STATIC_DOM",
                suggested_filename="page_0002.jpg",
            ),
        ],
    )

    # First attempt: Page 1 succeeds, Page 2 fails with 503
    async def mock_fetch_first(url, **kwargs):
        if "p1.jpg" in str(url):
            m = MagicMock()
            m.status_code = 200
            m.content = img_data_1
            m.raise_for_status = MagicMock()
            return m
        else:
            m = MagicMock()
            m.status_code = 503
            import httpx
            raise httpx.HTTPStatusError("503 Server Error", request=MagicMock(), response=m)

    with patch("httpx.AsyncClient.get", side_effect=mock_fetch_first):
        dl_res = await downloader.download_chapter(manifest, output_dir)
        assert dl_res["status"] == "PARTIAL"
        assert dl_res["downloaded"] == 1
        assert dl_res["failed"] == 1
        assert (output_dir / "page_0001.jpg").exists()
        assert not (output_dir / "page_0002.jpg").exists()

    # Second attempt: Retrying resumes page 1 and downloads page 2
    async def mock_fetch_second(url, **kwargs):
        m = MagicMock()
        m.status_code = 200
        m.content = img_data_2
        m.raise_for_status = MagicMock()
        return m

    with patch("httpx.AsyncClient.get", side_effect=mock_fetch_second):
        dl_res2 = await downloader.download_chapter(manifest, output_dir)
        assert dl_res2["status"] == "COMPLETE"
        assert dl_res2["resumed"] == 1
        assert dl_res2["downloaded"] == 1
        assert dl_res2["failed"] == 0
        assert (output_dir / "page_0002.jpg").exists()
