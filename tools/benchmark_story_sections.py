"""Benchmark local reconstruction against saved panel evidence in an isolated workspace."""
import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.llm.activity import activity_sink
from engine.llm.providers.ollama import OllamaProvider
from engine.story.models import PanelObservationEntity
from engine.story.section_planner import SectionPlanner
from engine.story.visual import ChapterUnderstanding, VisualStoryEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--model", default="qwen3.5:9b")
    args = parser.parse_args()
    report = json.loads((args.workspace / "story/panels_coverage_report.json").read_text(encoding="utf-8"))
    evidence = {}
    for path in (args.workspace / "story/vision_cache").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        evidence.setdefault(data.get("visual_summary"), []).append(data)
    observations = []
    for item in sorted(report["items"], key=lambda item: item["reading_order"]):
        if item["classification"] == "NON_STORY_CONTENT":
            continue
        summary = item.get("vision_description") or ""
        matches = evidence.get(summary, [])
        cached = matches[0] if len(matches) == 1 else {"visual_summary": summary}
        observations.append(PanelObservationEntity(
            panel_id=item["panel_id"], sequence_global=item["reading_order"],
            **{key: value for key, value in cached.items() if key in PanelObservationEntity.model_fields and key not in ("panel_id", "sequence_global")},
        ))
    output = Path(tempfile.mkdtemp(prefix="panelflow-story-benchmark-")).resolve()
    print(f"Isolated benchmark: {len(observations)} panels -> {output}", flush=True)
    usage = []
    def activity(value):
        if value["phase"] == "validating":
            usage.append(value)
            print(f"Model request: input={value.get('input_tokens')}, output={value.get('output_tokens')}, speed={value.get('tokens_per_second')} tokens/s", flush=True)
    provider = OllamaProvider(text_model=args.model, reasoning_model=args.model)
    token = activity_sink.set(activity)
    started = time.monotonic()
    try:
        result = asyncio.run(SectionPlanner().reconstruct(observations, provider, output,
            progress=lambda pct, message: print(f"{pct:.0%}: {message}", flush=True), metadata={"model": args.model}))
    finally:
        activity_sink.reset(token)
    chapter = ChapterUnderstanding.model_validate(result)
    VisualStoryEngine.validate_chapter(chapter, [item.panel_id for item in observations])
    elapsed = round(time.monotonic() - started, 2)
    cached_start = time.monotonic()
    cached = asyncio.run(SectionPlanner().reconstruct(observations, provider, output, metadata={"model": args.model}))
    summary = {"panels": len(observations), "elapsed_seconds": elapsed, "resume_seconds": round(time.monotonic() - cached_start, 3),
               "reconstruction": result["reconstruction_metadata"], "resume": cached["reconstruction_metadata"],
               "scenes": len(chapter.scenes), "beats": len(chapter.beats), "characters": len(chapter.characters), "model_usage": usage}
    (output / "result.json").write_text(json.dumps(result, default=str, indent=2), encoding="utf-8")
    (output / "benchmark.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
