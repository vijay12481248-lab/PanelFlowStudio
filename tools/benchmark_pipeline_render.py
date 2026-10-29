"""Compare frame rendering against a saved pre-change composer, including pixel hashes."""
import argparse
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path

from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, ProjectRecord
from engine.render.compiler import TimelineCompiler
from engine.render.composer import FrameComposer
from engine.render.models.profiles import RenderProfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--output", default="output/pipeline-performance/render-benchmark.json")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("baseline_composer", args.baseline)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    with SessionLocal() as db:
        project = db.get(ProjectRecord, args.project_id)
        panel = db.query(PanelRecord).filter(PanelRecord.project_id == project.id,
                    PanelRecord.status != "IGNORED", PanelRecord.sequence == 5).one()
        workspace = Path(project.workspace_path)
        asset = workspace / "panels" / panel.crop_filename
    results = []
    for preset in ("none", "pan_left", "slow_zoom_in"):
        state = {"scenes": [{"id": "benchmark", "duration_sec": args.frames / 30,
                 "layers": [{"id": "panel", "image_url": str(asset),
                             "duration_sec": args.frames / 30, "motion_preset": preset}]}]}
        plan = TimelineCompiler().compile(state, args.project_id, workspace, RenderProfile(width=1920, height=1080, fps=30))
        times = {"before": [], "after": []}
        hashes = {}
        for repeat in range(3):
            # Alternate order so the same implementation is not always first.
            names = ["before", "after"] if repeat % 2 == 0 else ["after", "before"]
            for name in names:
                composer = baseline.FrameComposer() if name == "before" else FrameComposer()
                digest = hashlib.sha256()
                start = time.perf_counter()
                for index in range(args.frames):
                    digest.update(composer.compose_frame(index, plan).tobytes())
                times[name].append(time.perf_counter() - start)
                hashes[name] = digest.hexdigest()
        assert hashes["before"] == hashes["after"], f"Pixel mismatch for {preset}"
        before, after = (statistics.median(times[name]) for name in ("before", "after"))
        results.append({"motion": preset, "frames": args.frames, "size": [1920, 1080],
                        "before_sec": before, "after_sec": after, "speedup": before / after,
                        "frame_bytes_identical": True, "sha256": hashes["after"], "runs": times})
    report = {"scope": "Frame composition plus byte hashing; excludes TTS, model inference and FFmpeg encoding",
              "source_asset": str(asset), "results": results}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
