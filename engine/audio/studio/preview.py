"""Preview stems for the Audio page: the same stems the export is built from, compressed to m4a for the browser, with waveform peaks.
Cached by a signature of everything that changes the sound, so a QA run or a reworded intent does not invalidate it."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from engine.audio.studio.mix import render_roles
from engine.audio.studio.peaks import file_peaks
from engine.audio.studio.plan import SoundPlan

_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
STEMS = ("dialogue", "music", "effects")


def audio_signature(plan: SoundPlan) -> str:
    cues = []
    for c in plan.cues:
        t = c.chosen()
        if t is None:
            continue  # a cue with no sound yet changes nothing
        cues.append([c.id, c.track, c.hit_t, c.anchor, c.t_in, c.t_out, c.gain_db, c.fade_in, c.fade_out, t.id, t.path, t.onset_s, t.peak_s, t.duration_s])
    tracks = [[t.id, t.gain_db, t.mute, t.duck_under] for t in plan.tracks]
    raw = json.dumps([plan.duration, plan.dialogue_path, tracks, cues], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_preview(plan: SoundPlan, out_dir: Path) -> dict:
    """dialogue/music/effects as .m4a plus 1200 peaks each. Re-uses out_dir when its preview.json has the plan's signature."""
    out_dir = Path(out_dir)
    sig = audio_signature(plan)
    meta = out_dir / "preview.json"
    if meta.is_file():
        old = json.loads(meta.read_text(encoding="utf-8"))
        if old.get("signature") == sig:
            return old
    out_dir.mkdir(parents=True, exist_ok=True)
    stems: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="audiostudio-pv-") as tmp:
        roles = render_roles(plan, Path(tmp))
        for name in STEMS:
            m4a = out_dir / f"{name}.m4a"
            p = subprocess.run([_FFMPEG, "-v", "error", "-y", "-i", str(roles[name]), "-c:a", "aac", "-b:a", "160k", str(m4a)],
                               capture_output=True, text=True, timeout=900)
            if p.returncode != 0:
                raise RuntimeError(f"ffmpeg failed encoding the {name} preview: {p.stderr.strip()[-200:]}")
            stems[name] = {"file": m4a.name, "peaks": file_peaks(roles[name], 1200)[0]}
    # the stems have these track gains baked in; the page plays a fader move as a trim relative to them until the next render
    result = {"signature": sig, "duration": plan.duration, "stems": stems, "gains": {t.id: t.gain_db for t in plan.tracks}}
    meta.write_text(json.dumps(result), encoding="utf-8")
    return result
