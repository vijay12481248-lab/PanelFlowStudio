"""Export a finished plan: stems, the music-and-effects pair, the loudness master, the cue sheet and the credits."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
from pathlib import Path

from engine.audio.studio.licence import licence_allowed
from engine.audio.studio.mix import _sum, render_cue, render_master, render_roles
from engine.audio.studio.plan import SoundPlan
from engine.audio.studio.qa import check_plan

_COLUMNS = ["id", "track", "kind", "intent", "hit_t", "anchor", "source", "licence", "url", "author", "model", "seed",
            "placement_error_ms", "status"]


def _row(cue) -> dict:
    p = cue.chosen().provenance if cue.chosen() else None
    return {"id": cue.id, "track": cue.track, "kind": cue.kind, "intent": cue.intent, "hit_t": cue.hit_t, "anchor": cue.anchor,
            "source": p.source if p else "", "licence": p.licence if p else "", "url": (p.url if p else "") or "",
            "author": (p.author if p else "") or "", "model": (p.model if p else "") or "", "seed": p.seed if p and p.seed is not None else "",
            "placement_error_ms": "" if cue.placement_error_ms is None else cue.placement_error_ms, "status": cue.status}


def export(plan: SoundPlan, out_dir: Path, target_lufs: float = -14.0, video_in: Path | None = None,
           allow_incomplete: bool = False) -> dict:
    """Write dialogue/music/effects/me/master wavs (+ master.mp4 with `video_in`), cuesheet.json/.csv, credits.txt, export.json."""
    pending = [c.id for c in plan.cues if c.status in ("draft", "needs_pick", "failed")]
    if pending and not allow_incomplete:
        raise ValueError(f"cues not finished: {', '.join(pending)} (source or pick them, or export with allow_incomplete)")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    findings = check_plan(plan, render_cue)  # also fills each hit cue's placement_error_ms
    with tempfile.TemporaryDirectory(prefix="audiostudio-export-") as tmp:
        roles = render_roles(plan, Path(tmp))
        for name in ("dialogue", "music", "effects"):
            shutil.copyfile(roles[name], out_dir / f"{name}.wav")
        _sum(out_dir / "me.wav", [(roles["music"], 0.0), (roles["effects"], 0.0)], plan.duration)
        loudness = render_master(plan, out_dir / "master.wav", target_lufs, video_in,
                                 out_dir / "master.mp4" if video_in else None, roles=roles)
    rows = [_row(c) for c in plan.cues]
    (out_dir / "cuesheet.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    with (out_dir / "cuesheet.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    credits = [f"{r['author'] or 'unknown'}: {r['url']} ({r['licence']})" for r in rows
               if r["licence"] and not licence_allowed(r["licence"], False) and licence_allowed(r["licence"], True)]
    (out_dir / "credits.txt").write_text("\n".join(credits) + ("\n" if credits else ""), encoding="utf-8")
    errors = sum(f.severity == "error" for f in findings)
    meta = {"plan_id": plan.id, "plan_version": plan.version, "loudness": loudness, "target_lufs": target_lufs,
            "findings": {"errors": errors, "warnings": len(findings) - errors, "items": [f.model_dump() for f in findings]}}
    (out_dir / "export.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    files = sorted(p.name for p in out_dir.iterdir() if p.is_file())
    return {"out_dir": str(out_dir), "files": files, "loudness": loudness, "findings": meta["findings"]}
