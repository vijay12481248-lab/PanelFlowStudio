import pytest
from pathlib import Path
from engine.acquisition.downloader.pipeline import DownloadPipeline
from engine.acquisition.adapters.local_folder import LocalFolderAdapter
from engine.acquisition.models import PageCandidate
from tests.fixtures.helpers import create_test_image_bytes

@pytest.mark.asyncio
async def test_pipeline_with_individual_failure_isolation(tmp_path: Path):
    source_dir = tmp_path / "incoming"
    source_dir.mkdir()

    # Create 3 pages: 1 valid, 1 corrupt (HTML error), 1 valid
    p1_bytes = create_test_image_bytes(100, 150, "blue")
    p2_corrupt = b"<html><body>500 Internal Server Error</body></html>"
    p3_bytes = create_test_image_bytes(100, 150, "red")

    (source_dir / "01.jpg").write_bytes(p1_bytes)
    (source_dir / "02.jpg").write_bytes(p2_corrupt)
    (source_dir / "03.jpg").write_bytes(p3_bytes)

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    adapter = LocalFolderAdapter()
    candidates = [
        PageCandidate(sequence=1, source_uri=str(source_dir / "01.jpg"), suggested_filename="01.jpg"),
        PageCandidate(sequence=2, source_uri=str(source_dir / "02.jpg"), suggested_filename="02.jpg"),
        PageCandidate(sequence=3, source_uri=str(source_dir / "03.jpg"), suggested_filename="03.jpg"),
    ]

    pipeline = DownloadPipeline(concurrency=2)
    results, manifest = await pipeline.execute(
        project_id="test-proj-1",
        workspace_path=workspace,
        adapter=adapter,
        candidates=candidates,
        source_meta={"type": "LOCAL_FOLDER"},
        rights_meta={"status": "PUBLIC_DOMAIN"},
        chapter_meta={"title": "Test Chapter"},
    )

    # Check that individual failure didn't block remaining downloads
    assert len(results) == 3
    assert results[0].success is True
    assert results[0].width == 100
    assert results[1].success is False
    assert "HTML error page" in results[1].error_message
    assert results[2].success is True
    assert results[2].width == 100

    # Manifest verification
    manifest_path = workspace / "manifest.json"
    assert manifest_path.exists()
    assert len(manifest.pages) == 3
    assert manifest.pages[0].status == "READY"
    assert manifest.pages[1].status == "FAILED"
    assert manifest.pages[2].status == "READY"

    # Check source files on disk
    assert (workspace / "source" / "page_0001.jpg").exists()
    assert (workspace / "source" / "page_0003.jpg").exists()

    # Now simulate fixing page 2 and retrying
    fixed_p2_bytes = create_test_image_bytes(100, 150, "green")
    (source_dir / "02.jpg").write_bytes(fixed_p2_bytes)

    retry_candidates = [
        PageCandidate(sequence=2, source_uri=str(source_dir / "02.jpg"), suggested_filename="02.jpg"),
    ]

    retry_results, updated_manifest = await pipeline.execute(
        project_id="test-proj-1",
        workspace_path=workspace,
        adapter=adapter,
        candidates=retry_candidates,
        source_meta={"type": "LOCAL_FOLDER"},
        rights_meta={"status": "PUBLIC_DOMAIN"},
        chapter_meta={"title": "Test Chapter"},
        existing_manifest=manifest,
    )

    assert len(retry_results) == 1
    assert retry_results[0].success is True
    assert (workspace / "source" / "page_0002.jpg").exists()
