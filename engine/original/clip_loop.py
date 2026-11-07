"""Controlled correction loop for one film shot (Phase 3 of the H3 skill; the policy is `.claude/skills/minimax-h3-video-production/references/regeneration.md`).

evaluate -> take the most severe defect -> apply ONE lever -> regenerate in an isolated workspace -> evaluate -> keep the better clip -> repeat until no
defect is left, the attempts are used up or no lever is left. Same inputs give the same clip (measured), so every attempt changes exactly one input
relative to the best clip so far. Every attempt (settings, report, decision) is appended to `<ws>/film/history/<shot>.json`; the attempt clips are kept in
`<ws>/film/attempts/<shot>/`. The shot's real clip in `film/clips` is only replaced when `apply=True`.

Levers implemented: `static_camera` (Static Shot sentence), `seed` (a new deterministic seed). Not implemented, so never chosen: redrawing the first frame,
editing the action text, `quiet` (needs speech detection, which the evaluator does not do). A defect with no lever left is reported, not hidden.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Callable

from engine.original import film
from engine.original.clip_eval import evaluate
from engine.original.models import OriginalStory

STATIC_CAMERA = "nothing; it is a Static Shot, fixed on a tripod, with no zoom, no pan and no tilt"
SEVERITY = ["temporal", "consistency", "camera", "artifacts", "motion", "audio"]  # a scene break matters more than a zoom, a zoom more than flicker
LEVERS = {"temporal": ["static_camera", "seed"], "consistency": ["seed"], "camera": ["static_camera", "seed"], "artifacts": ["seed"], "motion": ["seed"], "audio": []}

Generate = Callable[[Path, dict], Path]  # (attempt workspace, settings) -> clip path


def defects(report: dict, act_on_suspected: bool = False) -> list[dict]:
    """Flags worth acting on, most severe first. `suspected` flags are only acted on when asked (look at them first, regeneration.md)."""
    ok = ("confirmed", "suspected") if act_on_suspected else ("confirmed",)
    return sorted((f for f in report["flags"] if f["status"] in ok), key=lambda f: SEVERITY.index(f["axis"]) if f["axis"] in SEVERITY else 99)


def measure(report: dict, axis: str) -> float:
    """The number behind an axis's flag, so two clips can be compared by how bad the defect is (bigger = worse)."""
    c = report["camera"]
    return {"camera": max(abs(c["zoom_pct"]), abs(c["pan_x_pct"]), abs(c["pan_y_pct"])), "consistency": report["drift"]["max"], "artifacts": report["flicker"],
            "temporal": float(len(report["cuts_s"])), "motion": 1 / max(report["motion"], 0.05)}.get(axis, 1.0)


def better(new: dict, best: dict, act_on_suspected: bool = False) -> tuple[bool, str]:
    """Judge by the WORST defect, as the policy ranks them (SEVERITY): a clip with no defect beats one with; a worse worst-axis loses; a less severe one wins
    (even if it adds a minor flag: listed in the reason); on the same axis the new clip must be at least 25% smaller in the measured number."""
    nd, bd = defects(new, act_on_suspected), defects(best, act_on_suspected)
    if not bd:
        return False, "nothing to improve"
    if not nd:
        return True, "no defect left"
    rank = lambda f: SEVERITY.index(f["axis"]) if f["axis"] in SEVERITY else 99  # noqa: E731
    extra = sorted({f["axis"] for f in nd} - {f["axis"] for f in bd})
    note = f" (adds {extra})" if extra else ""
    for nf, bf in zip(nd, bd):  # worst defect first; a tie (within 25-33%) falls through to the next defect
        if rank(nf) != rank(bf):
            return rank(nf) > rank(bf), f"worst defect {bf['axis']} -> {nf['axis']}{note}"
        old, cur = measure(best, bf["axis"]), measure(new, nf["axis"])
        if cur < 0.75 * old or cur > old / 0.75:
            return cur < old, f"{nf['axis']} {old:.2f} -> {cur:.2f}{note}"
    return len(nd) < len(bd), f"no meaningful change{note}"


def next_lever(report: dict, settings: dict, tried: set, act_on_suspected: bool) -> tuple[str, str] | None:
    """(lever, axis) for the most severe defect that still has an untried lever; None when nothing can be done."""
    for f in defects(report, act_on_suspected):
        for lever in LEVERS.get(f["axis"], []):
            if lever == "static_camera" and settings.get("static_camera"):
                continue
            if (lever, f["axis"]) not in tried:
                return lever, f["axis"]
    return None


def apply_lever(lever: str, settings: dict, n: int) -> dict:
    new = dict(settings)
    if lever == "static_camera":
        new["static_camera"] = True
    else:  # seed: derived from the previous one and the attempt number, so it is reproducible
        new["seed"] = int(hashlib.sha256(f"{settings['seed']}|retry|{n}".encode()).hexdigest()[:12], 16)
    return new


def baseline_settings(story: OriginalStory, ws: Path, sid: str) -> dict:
    """Seed and voice mode the shot was made with (clips.json), else the default seed film.make_clips would use."""
    log = ws / "film" / "clips.json"
    entry = json.loads(log.read_text(encoding="utf-8")).get(sid, {}) if log.exists() else {}
    seed = entry.get("seed") or int(hashlib.sha256(f"{story.bible.premise.title}|{sid}|clip".encode()).hexdigest()[:12], 16)
    return {"seed": seed, "static_camera": False, "native_voice": bool(entry.get("native_voice"))}


def film_generate(story: OriginalStory, ws: Path, sid: str) -> Generate:
    """Generator that runs `film.make_clips` for one shot in its own workspace (frames copied in), so the story's real clips are never touched."""
    def run(work: Path, settings: dict) -> Path:
        (work / "film" / "frames").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ws / "film" / "frames" / f"{sid}.png", work / "film" / "frames" / f"{sid}.png")
        if (ws / "film" / "voices.json").exists():
            shutil.copy2(ws / "film" / "voices.json", work / "film" / "voices.json")
        res = film.make_clips(story, work, ids=[sid], seeds={sid: settings["seed"]}, native_voice=settings["native_voice"], camera=STATIC_CAMERA if settings["static_camera"] else None)
        if res["failed"]:
            raise RuntimeError(f"generation failed: {res['failed']}")
        return work / "film" / "clips" / f"{sid}.mp4"
    return run


def _brief(report: dict) -> dict:
    return {"flags": report["flags"], "zoom_pct": report["camera"]["zoom_pct"], "drift_max": report["drift"]["max"], "flicker": report["flicker"], "motion": report["motion"], "cuts_s": report["cuts_s"]}


def improve_clip(sid: str, ws: Path, generate: Generate, settings: dict, *, attempts: int = 3, expect_camera: str = "static", act_on_suspected: bool = False,
                 apply: bool = False, expect_audio: bool = True, now: Callable[[], float] = time.monotonic) -> dict:
    """Run the loop for shot `sid`. `generate(work_dir, settings)` returns the new clip; `settings` are the shot's current settings (`baseline_settings`).
    Returns {"best": path, "report": best report, "history": [...], "stopped": reason}."""
    fd = ws / "film"
    adir, hpath = fd / "attempts" / sid, fd / "history" / f"{sid}.json"
    adir.mkdir(parents=True, exist_ok=True)
    hpath.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(hpath.read_text(encoding="utf-8")) if hpath.exists() else []
    run_id = len({h["run"] for h in history}) + 1

    def log(rec: dict) -> None:
        history.append({"run": run_id, **rec})
        hpath.write_text(json.dumps(history, indent=1), encoding="utf-8")

    def ev(p: Path) -> dict:
        return evaluate(p, expect_camera=expect_camera, expect_audio=expect_audio)

    first = fd / "clips" / f"{sid}.mp4"
    if first.exists():
        base_path = adir / f"r{run_id}_a0.mp4"
        shutil.copy2(first, base_path)
    else:
        base_path = adir / f"r{run_id}_a0.mp4"
        shutil.copy2(generate(adir / f"r{run_id}_a0_work", settings), base_path)
    best_path, best_set, best = base_path, settings, ev(base_path)
    log({"attempt": 0, "lever": None, "settings": settings, "clip": best_path.name, "report": _brief(best), "decision": "baseline", "reason": "starting clip"})
    tried: set = set()
    stopped = None
    for n in range(1, attempts + 1):
        if not defects(best, act_on_suspected):
            break
        pick = next_lever(best, best_set, tried, act_on_suspected)
        if pick is None:
            stopped = "no lever left for the remaining defect"
            break
        lever, axis = pick
        tried.add((lever, axis))
        new_set = apply_lever(lever, best_set, n)
        t0 = now()
        clip = adir / f"r{run_id}_a{n}.mp4"
        shutil.copy2(generate(adir / f"r{run_id}_a{n}_work", new_set), clip)
        rep = ev(clip)
        win, why = better(rep, best, act_on_suspected)
        log({"attempt": n, "lever": lever, "for_axis": axis, "settings": new_set, "clip": clip.name, "report": _brief(rep), "elapsed_s": round(now() - t0, 1),
             "decision": "kept" if win else "discarded", "reason": why})
        if win:
            best_path, best_set, best = clip, new_set, rep
    left = defects(best, act_on_suspected)
    look = [f"{f['axis']} ({f['status']})" for f in best["flags"] if f["status"] == "suspected" and f not in left]
    stopped = stopped or ("attempts used up" if left else "no confirmed defect left" + (f"; SUSPECTED remain, look at the frames: {look}" if look else ""))
    if apply and best_path != base_path:
        shutil.copy2(best_path, first)
    return {"best": str(best_path), "settings": best_set, "report": _brief(best), "applied": bool(apply and best_path != base_path), "stopped": stopped,
            "defects_left": [f"{f['axis']} ({f['status']})" for f in left], "needs_look": look, "history": [h for h in history if h["run"] == run_id]}


def main() -> None:  # python -m engine.original.clip_loop <story_dir> <shot> [--attempts 3] [--camera any] [--suspected] [--apply]
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("story_dir")
    ap.add_argument("shot")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--camera", default="static", choices=["static", "any"])
    ap.add_argument("--suspected", action="store_true", help="also act on suspected flags (look at the frames first)")
    ap.add_argument("--apply", action="store_true", help="replace film/clips/<shot>.mp4 with the best clip")
    a = ap.parse_args()
    ws = Path(a.story_dir)
    story = OriginalStory.model_validate(json.loads((ws / "story.json").read_text(encoding="utf-8")))
    out = improve_clip(a.shot, ws, film_generate(story, ws, a.shot), baseline_settings(story, ws, a.shot), attempts=a.attempts, expect_camera=a.camera,
                       act_on_suspected=a.suspected, apply=a.apply)
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=1))
    for h in out["history"]:
        print(h["attempt"], h["lever"], h["decision"], h["reason"], [f"{f['axis']}:{f['status']}" for f in h["report"]["flags"]])


if __name__ == "__main__":
    main()
