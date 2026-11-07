"""Controlled correction loop for one film shot (Phase 3 of the H3 skill; the policy is `.claude/skills/minimax-h3-video-production/references/regeneration.md`).

evaluate -> take the most severe defect -> apply ONE lever -> regenerate in an isolated workspace -> evaluate -> keep the better clip -> repeat until no
defect is left, the attempts are used up or no lever is left. Same inputs give the same clip (measured), so every attempt changes exactly one input
relative to the best clip so far. Every attempt (settings, report, decision) is appended to `<ws>/film/history/<shot>.json`; the attempt clips are kept in
`<ws>/film/attempts/<shot>/`. The shot's real clip in `film/clips` is only replaced when `apply=True`.

Levers: `static_camera` (Static Shot sentence; the default for new clips, so it matters for clips made with a push-in), `simplify_action` (a rule-based cut of the shot's motion text, see `simplify_motion`), `redraw_frame` (a new first
frame through the one art workflow; needs a runner), `seed` (a new deterministic seed). Not implemented, so never chosen: `quiet` (needs speech detection, which the
evaluator does not do). A defect with no lever left is reported, not hidden. The lever ORDER per defect is a hypothesis; the history shows which one worked.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from engine.original import film
from engine.original.animate import STATIC_CAMERA
from engine.original.clip_eval import evaluate
from engine.original.models import OriginalStory

SEVERITY = ["temporal", "consistency", "camera", "artifacts", "motion", "audio"]  # a scene break matters more than a zoom, a zoom more than flicker
LEVERS = {"temporal": ["static_camera", "widen_frame", "simplify_action", "redraw_frame", "seed"], "consistency": ["simplify_action", "redraw_frame", "seed"],
          "camera": ["static_camera", "seed"], "artifacts": ["seed"], "motion": ["seed"], "audio": []}
DEFAULT_LEVERS = frozenset({"static_camera", "simplify_action", "seed"})  # redraw_frame and widen_frame are added when a frame runner is available
FRAME_LEVERS = frozenset({"redraw_frame", "widen_frame"})
SHOT_LADDER = ["extreme_close", "close", "medium", "wide"]  # widen_frame moves the FIRST FRAME one step to the right; the clip keeps the shot's own size (camera sentence, length)
LIGHT = re.compile(r"\b(light|lights|glow|glows|glowing|flash|flashes|flare|flares|beam|beams|shaft|shafts|lightning|ray|rays|shine|shines|shining|blaze|blazes|gleam|gleams|bright|brighter|brightens)\b", re.I)

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


def simplify_motion(text: str, axis: str = "") -> str | None:
    """A shorter motion text, by rule (generic, nothing per story), or None when there is nothing to cut. By convention the FIRST clause is the main action;
    the later ones are secondary actions and expressions that H3 over-extends. For a colour/lighting defect (`consistency`) only the clauses that name a light event
    are dropped (a growing glow washes the whole picture); for any other defect everything after the first clause is dropped."""
    clauses = [c.strip() for c in text.strip().rstrip(".").split(",") if c.strip()]
    if axis == "consistency":
        kept = [c for c in clauses if not LIGHT.search(c)]
        return ", ".join(kept) if kept and len(kept) < len(clauses) else None
    return clauses[0] if len(clauses) > 1 else None


def widen(shot: str | None) -> str | None:
    """The next wider shot size, or None when already wide (or unknown)."""
    return SHOT_LADDER[SHOT_LADDER.index(shot) + 1] if shot in SHOT_LADDER[:-1] else None


def simplifiable(settings: dict, axis: str) -> bool:
    if settings.get("shots"):
        return any(simplify_motion(sh["action"], axis) not in (None, sh["action"]) for sh in settings["shots"])
    return simplify_motion(settings.get("motion") or "", axis) not in (None, settings.get("motion"))


def next_lever(report: dict, settings: dict, tried: set, act_on_suspected: bool, available: frozenset = DEFAULT_LEVERS) -> tuple[str, str] | None:
    """(lever, axis) for the most severe defect that still has an untried, usable lever; None when nothing can be done."""
    for f in defects(report, act_on_suspected):
        for lever in LEVERS.get(f["axis"], []):
            if lever not in available or (lever, f["axis"]) in tried:
                continue
            if lever == "static_camera" and settings.get("camera") == STATIC_CAMERA:
                continue
            if lever == "widen_frame" and widen(settings.get("frame_shot")) is None:
                continue
            if lever == "simplify_action" and not simplifiable(settings, f["axis"]):
                continue
            return lever, f["axis"]
    return None


def apply_lever(lever: str, settings: dict, n: int, axis: str = "") -> dict:
    new = dict(settings)
    if lever == "static_camera":
        new["camera"] = STATIC_CAMERA
    elif lever == "simplify_action":
        if settings.get("shots"):  # a long take: simplify what each shot shows
            new["shots"] = [{**sh, "action": simplify_motion(sh["action"], axis) or sh["action"]} for sh in settings["shots"]]
        else:
            new["motion"] = simplify_motion(settings["motion"], axis)
    elif lever == "redraw_frame":
        new["frame_attempt"] = settings.get("frame_attempt", 0) + 1
    elif lever == "widen_frame":
        new["frame_shot"] = widen(settings["frame_shot"])
    else:  # seed: derived from the previous one and the attempt number, so it is reproducible
        new["seed"] = int(hashlib.sha256(f"{settings['seed']}|retry|{n}".encode()).hexdigest()[:12], 16)
    return new


def baseline_settings(story: OriginalStory, ws: Path, sid: str) -> dict:
    """What the shot was made with: seed and voice mode (clips.json, else the default seed film.make_clips would use), motion text, first-frame attempt."""
    log = ws / "film" / "clips.json"
    entry = json.loads(log.read_text(encoding="utf-8")).get(sid, {}) if log.exists() else {}
    seed = entry.get("seed") or int(hashlib.sha256(f"{story.bible.premise.title}|{sid}|clip".encode()).hexdigest()[:12], 16)
    panel = next((p for p in story.panels if p.id == sid), None)
    flog = ws / "film" / "frames.json"
    frame = json.loads(flog.read_text(encoding="utf-8")).get(sid, {}).get("attempt", 0) if flog.exists() else 0
    m = re.search(r"The camera does (.+?)\. Single continuous take", entry.get("prompt", ""))  # the sentence the clip was really made with (older clips used a push-in)
    camera = m.group(1) if m else ((panel.camera if panel else "") or STATIC_CAMERA)
    return {"seed": seed, "camera": camera, "native_voice": bool(entry.get("native_voice")), "motion": panel.motion if panel else "", "shots": [dict(x) for x in panel.shots] if panel else [], "frame_attempt": frame,
            "frame_shot": panel.shot if panel else None}


def _with(story: OriginalStory, sid: str, **update) -> OriginalStory:
    """A copy of the story with one panel's fields replaced (the real story object is never touched)."""
    return story.model_copy(update={"panels": [p.model_copy(update=update) if p.id == sid else p for p in story.panels]})


def film_generate(story: OriginalStory, ws: Path, sid: str, runner=None, baseline: dict | None = None) -> Generate:
    """Generator that runs `film.make_clips` for one shot in its own workspace, so the story's real clips are never touched. A changed `motion` is applied to a copy
    of the story. A changed `frame_attempt` or `frame_shot` (vs `baseline`) draws a new first frame with `film.make_frames` (needs `runner`, an `art.ComfyRunner`; the
    frame uses the wider shot size, the clip keeps the shot's own); otherwise the original frame is copied."""
    base = baseline or {}

    def run(work: Path, settings: dict) -> Path:
        story2 = story
        if settings.get("motion") is not None and any(p.id == sid and p.motion != settings["motion"] for p in story.panels):
            story2 = _with(story, sid, motion=settings["motion"])
        if settings.get("shots"):
            story2 = _with(story2, sid, shots=settings["shots"])
        (work / "film" / "frames").mkdir(parents=True, exist_ok=True)
        redraw = settings.get("frame_attempt", 0) != base.get("frame_attempt", 0) or settings.get("frame_shot") != base.get("frame_shot")
        if redraw:
            if runner is None:
                raise RuntimeError("redrawing the first frame needs a frame runner")
            story_frame = _with(story2, sid, shot=settings["frame_shot"]) if settings.get("frame_shot") else story2
            film.make_frames(story_frame, work, runner, ids=[sid], rerolls={sid: settings.get("frame_attempt", 0)})
        else:
            shutil.copy2(ws / "film" / "frames" / f"{sid}.png", work / "film" / "frames" / f"{sid}.png")
        if (ws / "film" / "voices.json").exists():
            shutil.copy2(ws / "film" / "voices.json", work / "film" / "voices.json")
        res = film.make_clips(story2, work, ids=[sid], seeds={sid: settings["seed"]}, native_voice=settings["native_voice"], camera=settings.get("camera"))
        if res["failed"]:
            raise RuntimeError(f"generation failed: {res['failed']}")
        return work / "film" / "clips" / f"{sid}.mp4"
    return run


def _brief(report: dict) -> dict:
    return {"flags": report["flags"], "zoom_pct": report["camera"]["zoom_pct"], "drift_max": report["drift"]["max"], "flicker": report["flicker"], "motion": report["motion"], "cuts_s": report["cuts_s"]}


def improve_clip(sid: str, ws: Path, generate: Generate, settings: dict, *, attempts: int = 3, expect_camera: str = "static", act_on_suspected: bool = False,
                 apply: bool = False, expect_audio: bool = True, levers: frozenset = DEFAULT_LEVERS, planned_cuts: list[float] | None = None, now: Callable[[], float] = time.monotonic) -> dict:
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
        return evaluate(p, expect_camera=expect_camera, expect_audio=expect_audio, planned_cuts=planned_cuts)

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
        pick = next_lever(best, best_set, tried, act_on_suspected, levers)
        if pick is None:
            stopped = "no lever left for the remaining defect"
            break
        lever, axis = pick
        tried.add((lever, axis))
        new_set = apply_lever(lever, best_set, n, axis)
        t0 = now()
        clip = adir / f"r{run_id}_a{n}.mp4"
        shutil.copy2(generate(adir / f"r{run_id}_a{n}_work", new_set), clip)
        rep = ev(clip)
        win, why = better(rep, best, act_on_suspected)
        log({"attempt": n, "lever": lever, "for_axis": axis, "settings": new_set, "changed": {k: [best_set.get(k), v] for k, v in new_set.items() if best_set.get(k) != v}, "clip": clip.name, "report": _brief(rep), "elapsed_s": round(now() - t0, 1),
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
    ap.add_argument("--no-redraw", action="store_true", help="do not use the redraw_frame lever (no art runner)")
    a = ap.parse_args()
    ws = Path(a.story_dir)
    story = OriginalStory.model_validate(json.loads((ws / "story.json").read_text(encoding="utf-8")))
    base = baseline_settings(story, ws, a.shot)
    runner = None
    if not a.no_redraw:
        from engine.original import art as art_mod

        runner = art_mod.ComfyRunner()
    out = improve_clip(a.shot, ws, film_generate(story, ws, a.shot, runner, base), base, attempts=a.attempts, expect_camera=a.camera,
                       act_on_suspected=a.suspected, apply=a.apply, levers=DEFAULT_LEVERS | (FRAME_LEVERS if runner else frozenset()),
                       planned_cuts=[x['at'] for x in base.get('shots', [])[1:]] or None)
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=1))
    for h in out["history"]:
        print(h["attempt"], h["lever"], h["decision"], h["reason"], h.get("changed", ""), [f"{f['axis']}:{f['status']}" for f in h["report"]["flags"]])


if __name__ == "__main__":
    main()
