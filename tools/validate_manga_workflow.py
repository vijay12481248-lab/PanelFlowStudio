"""Repeatable real-source validation; uses production import, segmentation and vision modules."""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from engine.acquisition.adapters.generic_web import GenericAuthorizedWebAdapter
from engine.acquisition.downloader.pipeline import DownloadPipeline
from engine.acquisition.models import AcquisitionManifest
from engine.imaging.panels import panel_detector
from engine.llm.providers.ollama import OllamaProvider
from engine.story.visual import VisualStoryEngine


async def main(args):
    workspace = Path(args.output).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    adapter = GenericAuthorizedWebAdapter()
    inspection = adapter.inspect(args.url)
    if not inspection.is_valid or not inspection.chapters:
        raise ValueError(inspection.error or "No chapter discovered")
    chapter = inspection.chapters[0]
    existing = None
    manifest_path = workspace / "manifest.json"
    if manifest_path.exists():
        existing = AcquisitionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    results, manifest = await DownloadPipeline().execute(
        project_id="manga_validation", workspace_path=workspace, adapter=adapter,
        candidates=adapter.list_pages(chapter), source_meta=inspection.metadata.model_dump(),
        rights_meta={"purpose": "user-requested workflow validation"}, chapter_meta=chapter.model_dump(),
        progress_callback=lambda p, m: print(m, flush=True), existing_manifest=existing,
    )
    if any(not result.success for result in results):
        raise ValueError("Asset download failed; inspect manifest and retry")
    panels_dir = workspace / "panels"
    panels_dir.mkdir(exist_ok=True)
    items = []
    panel_data = []
    panel_index = workspace / "panels.json"
    if panel_index.exists():
        panel_data = json.loads(panel_index.read_text(encoding="utf-8"))
        items = [SimpleNamespace(id=p["panel_id"], sequence=p["reading_order"], crop_filename=p["panel_id"] + ".png") for p in panel_data]
    else:
        for page in sorted(manifest.pages, key=lambda p: p.sequence):
            source = workspace / "source" / page.filename
            with Image.open(source) as image:
                detected = panel_detector.detect_panels(source, profile="WEBTOON", page_id=str(page.sequence))
                for box in detected:
                    panel_id = f"panel_{len(items) + 1:04d}"
                    filename = f"{panel_id}.png"
                    image.crop((box.x, box.y, box.x + box.width, box.y + box.height)).save(panels_dir / filename)
                    items.append(SimpleNamespace(id=panel_id, sequence=len(items) + 1, crop_filename=filename))
                    panel_data.append({"panel_id": panel_id, "source_image": page.filename,
                                       "bbox": [box.x, box.y, box.width, box.height], "reading_order": len(items)})
    for index, panel in enumerate(panel_data):
        panel["previous_panel"] = panel_data[index - 1]["panel_id"] if index else None
        panel["next_panel"] = panel_data[index + 1]["panel_id"] if index + 1 < len(panel_data) else None
    (workspace / "panels.json").write_text(json.dumps(panel_data, indent=2), encoding="utf-8")
    report = {"source_url": args.url, "title": inspection.title_suggestion,
              "downloaded_images": len(results), "panels": len(items),
              "source_sha256": [hashlib.sha256((workspace / "source" / p.filename).read_bytes()).hexdigest() for p in manifest.pages]}
    print(json.dumps(report, indent=2), flush=True)
    (workspace / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.analyze:
        provider = OllamaProvider(timeout=300, num_ctx=16384)
        engine = VisualStoryEngine()
        document = await engine.analyze("manga_validation", workspace, items, [], provider,
                                        progress=lambda p, m: print(m, flush=True),
                                        settings={"language": "en", "story_style": "Cinematic", "narration_length": "Medium"})
        (workspace / "story/narrative.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
        script = await engine.narrate(document, provider)
        (workspace / "script").mkdir(exist_ok=True)
        (workspace / "script/script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
        print(f"Chapter understood: {len(document.scenes)} scenes, {len(script.segments)} narration segments", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", default="output/manga_workflow_validation")
    parser.add_argument("--analyze", action="store_true")
    asyncio.run(main(parser.parse_args()))
