import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.acquisition.adapters.local_folder import LocalFolderAdapter
from engine.acquisition.adapters.zip_archive import ZipArchiveAdapter
from engine.acquisition.adapters.generic_web import GenericAuthorizedWebAdapter
from engine.acquisition.models import ChapterInfo, PageCandidate
from tests.fixtures.helpers import create_test_image_bytes, create_test_zip_archive

@pytest.mark.asyncio
async def test_local_folder_adapter(tmp_path: Path):
    folder = tmp_path / "comic_pages"
    folder.mkdir()

    # Create 3 pages with non-padded names to test natural sorting
    img1 = create_test_image_bytes(100, 100, "red")
    img2 = create_test_image_bytes(100, 100, "green")
    img10 = create_test_image_bytes(100, 100, "blue")

    (folder / "page_10.jpg").write_bytes(img10)
    (folder / "page_1.jpg").write_bytes(img1)
    (folder / "page_2.jpg").write_bytes(img2)

    adapter = LocalFolderAdapter()
    assert adapter.can_handle(folder)

    inspection = adapter.inspect(folder)
    assert inspection.is_valid
    assert inspection.total_pages_detected == 3
    assert len(inspection.chapters) == 1

    chapter = inspection.chapters[0]
    pages = adapter.list_pages(chapter)
    assert len(pages) == 3
    # Check deterministic ordering: page_1, page_2, page_10
    assert Path(pages[0].source_uri).name == "page_1.jpg"
    assert Path(pages[1].source_uri).name == "page_2.jpg"
    assert Path(pages[2].source_uri).name == "page_10.jpg"

    # Test download page
    dest = tmp_path / "output" / "page_0001.jpg"
    res = await adapter.download_page(pages[0], dest)
    assert res.success
    assert res.width == 100
    assert res.height == 100
    assert dest.exists()

@pytest.mark.asyncio
async def test_zip_archive_adapter(tmp_path: Path):
    zip_path = tmp_path / "sample.cbz"
    img1 = create_test_image_bytes(120, 160, "yellow")
    img2 = create_test_image_bytes(120, 160, "purple")

    create_test_zip_archive(zip_path, {
        "ch1/p02.png": img2,
        "ch1/p01.png": img1,
        "__MACOSX/._p01.png": b"garbage",  # should be ignored
    })

    adapter = ZipArchiveAdapter()
    assert adapter.can_handle(zip_path)

    inspection = adapter.inspect(zip_path)
    assert inspection.is_valid
    assert inspection.total_pages_detected == 2

    chapter = inspection.chapters[0]
    pages = adapter.list_pages(chapter)
    assert len(pages) == 2
    assert "p01.png" in pages[0].source_uri
    assert "p02.png" in pages[1].source_uri

    dest = tmp_path / "out_zip" / "page_0001.png"
    res = await adapter.download_page(pages[0], dest)
    assert res.success
    assert res.width == 120
    assert res.height == 160
    assert dest.exists()

@pytest.mark.asyncio
async def test_generic_web_adapter_direct_image(tmp_path: Path):
    adapter = GenericAuthorizedWebAdapter()
    assert adapter.can_handle("https://example.com/comics/ch1/page01.jpg")
    assert not adapter.can_handle("c:/local/path/file.png")

    img_data = create_test_image_bytes(100, 100, "cyan")

    dest = tmp_path / "web_out" / "page_0001.jpg"
    candidate = PageCandidate(sequence=1, source_uri="https://example.com/page01.jpg")

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = img_data
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        res = await adapter.download_page(candidate, dest)
        assert res.success
        assert res.width == 100
        assert dest.exists()
