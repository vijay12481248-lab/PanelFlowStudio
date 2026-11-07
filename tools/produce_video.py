"""One abstract brief -> a finished informative video, end to end, with long takes (docs/H3_CLIP_EVAL.md, "Director").

  python tools/produce_video.py "<brief>" <slug> [--seconds 60] [--max-take 15] [--stage plan|frames|clips|qa|master|all]

Stages are resumable (files under output/Original_Stories/<slug>/):
  plan    the Director (local LLM) writes the whole production plan: story.json + plan.md (read it)
  frames  one first frame per take through the art workflow; each frame is counted (exactly the cast, no extras) and redrawn up to 3 times if not
  clips   one long H3 take per panel (as long as H3 allows), narration laid over at the master; if a take cannot be generated the whole plan is made again with shorter takes
  qa      every clip: clip_eval + character presence + cast counts, written to qa.json
  master  cut, narration mix, captions (SRT), title
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.llm.registry import llm_registry  # noqa: E402
from engine.original import art as art_mod  # noqa: E402
from engine.original import clip_identity as ci  # noqa: E402
from engine.original import director, film, film_master  # noqa: E402
from engine.original.animate import release_ollama  # noqa: E402
from engine.original.clip_eval import evaluate  # noqa: E402
from engine.original.models import OriginalStory  # noqa: E402

ROOT = Path("output/Original_Stories")


def plan_md(story: OriginalStory) -> str:
    out = [f"# {story.bible.premise.title}\n\n{story.bible.premise.logline}\n\n## Cast\n"]
    out += [f"- **{c.name}** ({c.species}, {c.age_group}): {c.look}" for c in story.bible.characters]
    out += ["\n## Places\n"] + [f"- **{x.name}**: {x.look}" for x in story.bible.locations]
    for p in story.panels:
        out += [f"\n## Take {p.id} - {p.seconds:.0f} s - {next(x.name for x in story.bible.locations if x.id == p.location_id)}\n", f"*Narration:* {p.dialogue[0].text}\n"]
        out += [f"- [{s['at']:.1f} s] {s['framing']}{' / ' + s['camera'] if s['camera'] else ''}: {s['action']}" for s in p.shots]
    return "\n".join(out) + "\n"


async def stage_plan(brief: str, ws: Path, total: float, max_take: float) -> OriginalStory:
    story = await director.direct(brief, llm_registry.get_ollama_provider(), total, max_take, progress=lambda p, m: print(f"  plan {p:.0%} {m}", flush=True))
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "story.json").write_text(story.model_dump_json(indent=1), encoding="utf-8")
    (ws / "plan.md").write_text(plan_md(story), encoding="utf-8")
    return story


async def frame_cast_ok(story: OriginalStory, panel, png: bytes, provider) -> list[str]:
    """Problems with a first frame: any kind of character counted differently from the plan (None = the two answers disagreed, not a problem)."""
    bad = []
    for kind, names in film.cast_kinds(story, panel.character_ids).items():
        n = await ci.count_png(provider, png, kind)
        if n is not None and n != len(names):
            bad.append(f"{kind}: counted {n}, planned {len(names)}")
    return bad


async def stage_frames(story: OriginalStory, ws: Path) -> dict:
    runner, provider = art_mod.ComfyRunner(), llm_registry.get_ollama_provider()
    rerolls: dict[str, int] = {}
    for attempt in range(4):
        film.make_frames(story, ws, runner, ids=None, rerolls=rerolls)
        bad = {}
        for p in story.panels:
            problems = await frame_cast_ok(story, p, (ws / "film" / "frames" / f"{p.id}.png").read_bytes(), provider)
            if problems:
                bad[p.id] = problems
        print(f"  frames pass {attempt + 1}: {'all counts match the plan' if not bad else bad}", flush=True)
        if not bad:
            return {"redraws": rerolls}
        if attempt == 3:
            return {"redraws": rerolls, "unresolved": bad}
        for pid in bad:
            rerolls[pid] = rerolls.get(pid, 0) + 1


def stage_clips(story: OriginalStory, ws: Path) -> dict:
    release_ollama()
    res = film.make_clips(story, ws, progress=lambda p, m: print(f"  clips {p:.0%} {m}", flush=True))
    if res["failed"]:
        raise RuntimeError(f"take(s) could not be generated: {res['failed']}")
    return res


async def stage_qa(story: OriginalStory, ws: Path) -> dict:
    provider = llm_registry.get_ollama_provider()
    qa = {}
    for p in story.panels:
        clip = ws / "film" / "clips" / f"{p.id}.mp4"
        rep = evaluate(clip, expect_camera="static", expect_audio=False)  # the narration is mixed at the master: the clip itself is silent by design
        chars = [(c.name, c.look) for c in story.bible.characters if c.id in p.character_ids]
        ident = await ci.check(clip, chars, provider)
        counts = await ci.count_check(clip, {k: len(v) for k, v in film.cast_kinds(story, p.character_ids).items()}, provider)
        qa[p.id] = {"eval": {k: rep[k] for k in ("frames", "seconds", "camera", "cuts_s", "flicker", "drift", "motion")}, "flags": rep["flags"] + ident["flags"] + counts["flags"],
                    "presence": {n: d["presence"] for n, d in ident["characters"].items()}, "counts": counts["counts"]}
        print(f"  qa {p.id}: {rep['seconds']} s, flags {[f['axis'] + ':' + f['status'][:4] for f in qa[p.id]['flags']]}, presence {qa[p.id]['presence']}, counts {counts['counts']}", flush=True)
    (ws / "qa.json").write_text(json.dumps(qa, indent=1), encoding="utf-8")
    return qa


def stage_master(story: OriginalStory, ws: Path) -> dict:
    return film_master.render(story, ws, cues=None, name="explainer", title=story.bible.premise.title)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("slug")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--max-take", type=float, default=director.MAX_TAKE)
    ap.add_argument("--stage", default="all", choices=["plan", "frames", "clips", "qa", "master", "all"])
    a = ap.parse_args()
    ws = ROOT / a.slug
    want = lambda s: a.stage in ("all", s)  # noqa: E731
    t0 = time.time()
    story = asyncio.run(stage_plan(a.brief, ws, a.seconds, a.max_take)) if want("plan") and not (a.stage == "all" and (ws / "story.json").exists()) else OriginalStory.model_validate_json((ws / "story.json").read_text(encoding="utf-8"))
    print(f"plan: {len(story.panels)} takes of {story.panels[0].seconds:.0f} s ({round(time.time() - t0)} s)", flush=True)
    if want("frames"):
        print("frames:", asyncio.run(stage_frames(story, ws)), flush=True)
    if want("clips"):
        print("clips:", json.dumps(stage_clips(story, ws)), flush=True)
    if want("qa"):
        asyncio.run(stage_qa(story, ws))
    if want("master"):
        print("master:", stage_master(story, ws), flush=True)
    print(f"done in {round((time.time() - t0) / 60, 1)} min", flush=True)


if __name__ == "__main__":
    main()
