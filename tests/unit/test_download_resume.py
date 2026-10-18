import asyncio
import hashlib

from engine.acquisition.downloader.pipeline import DownloadPipeline
from engine.acquisition.models import DownloadedPageResult, PageCandidate


def test_verified_sources_resume_and_corrupt_files_redownload(tmp_path):
    class Adapter:
        calls = 0

        async def download_page(self, page, target, cancel):
            self.calls += 1
            target.write_bytes(b"verified source bytes")
            return DownloadedPageResult(sequence=page.sequence, source_uri=page.source_uri,
                                        target_path=target, filename=target.name, width=800, height=1600,
                                        byte_size=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())

    adapter = Adapter()
    pipeline = DownloadPipeline()
    kwargs = dict(project_id="project", workspace_path=tmp_path, adapter=adapter,
                  candidates=[PageCandidate(sequence=1, source_uri="https://example.org/1.jpg")],
                  source_meta={}, rights_meta={}, chapter_meta={})
    results, manifest = asyncio.run(pipeline.execute(**kwargs))
    results, manifest = asyncio.run(pipeline.execute(**kwargs, existing_manifest=manifest))
    assert adapter.calls == 1
    assert results[0].success
    results[0].target_path.write_bytes(b"corrupt")
    asyncio.run(pipeline.execute(**kwargs, existing_manifest=manifest))
    assert adapter.calls == 2
