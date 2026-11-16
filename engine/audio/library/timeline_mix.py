"""Mix the Video Studio timeline's sounds (A2 voice, A3 music, A4 effects) onto the rendered picture master.

Reuses the Sound Plan mixer (engine/audio/studio/mix.py): each timeline item becomes a ready cue whose take is the item's part of the sound,
so music ducks under voice and the clip sound, the master is limited and normalised to the loudness target exactly as the Audio page does.
The clip sound already in the master (A1) is kept as part of the dialogue stem.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import soundfile as sf

from engine.audio.library.store import SR, SoundStore
from engine.audio.studio.measure import measure_take
from engine.audio.studio.mix import render_master, render_roles
from engine.audio.studio.plan import Cue, Provenance, SoundPlan, Take, Track

_ROLE = {"voice": "dialogue", "music": "music", "effect": "sfx"}


def _probe(video: Path) -> tuple[float, float, bool]:
    from engine.chronoflow.media_tools import probe
    info = probe(video)
    return float(info["fps"]), float(info["duration"]), bool(info["has_audio"])


def check_items(items: list[dict[str, Any]], store: SoundStore) -> list[dict[str, Any]]:
    """Validated items: {sound, version, track, start, in, out, gain_db, fade_in, fade_out}. Bad input is a ValueError naming the item."""
    out = []
    for i, raw in enumerate(items or []):
        try:
            sid, track = str(raw["sound"]), str(raw.get("track", "effect"))
            if track not in _ROLE:
                raise ValueError(f"track must be voice, music or effect, not {track!r}")
            s = store.load(sid)
            v = int(raw.get("version") or s.current)
            dur = s.version(v).duration_s
            a, b = float(raw.get("in", 0.0)), float(raw.get("out", dur))
            a, b = max(0.0, min(a, dur)), max(0.0, min(b, dur))
            if b - a < 0.01:
                raise ValueError("the item is empty")
            out.append({"sound": sid, "version": v, "track": track, "start": max(0.0, float(raw.get("start", 0.0))), "in": a, "out": b,
                        "gain_db": max(-60.0, min(float(raw.get("gain_db", 0.0)), 24.0)),
                        "fade_in": max(0.0, float(raw.get("fade_in", 0.0))), "fade_out": max(0.0, float(raw.get("fade_out", 0.0))),
                        "provenance": s.provenance})
        except FileNotFoundError:
            raise ValueError(f"sound {i + 1}: {raw.get('sound')!r} is not in the library (deleted?)")
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"sound {i + 1}: {e}")
    return out


def mix_onto_video(video: Path, items: list[dict[str, Any]], store: SoundStore | None = None, target_lufs: float = -14.0) -> dict:
    """Replace the video's sound with clip sound + timeline sounds, mixed and normalised. Returns the loudness measured on the result."""
    store = store or SoundStore()
    video = Path(video)
    ok = check_items(items, store)
    if not ok:
        return {}
    fps, duration, has_audio = _probe(video)
    with tempfile.TemporaryDirectory(prefix="pf-tl-mix-") as tmp:
        tmp_p = Path(tmp)
        tracks = [Track(id=r, role=r, duck_under="dialogue" if r == "music" else None) for r in ("dialogue", "music", "sfx", "ambience", "foley")]
        plan = SoundPlan(id="timeline", video_path=str(video), fps=fps, duration=duration, dialogue_path=str(video) if has_audio else None,
                         keep_original_audio=True, tracks=tracks)
        for n, it in enumerate(ok):
            x = store.read(it["sound"], it["version"])[int(it["in"] * SR):int(it["out"] * SR)]
            part = tmp_p / f"item_{n:03d}.wav"
            sf.write(str(part), x, SR, subtype="FLOAT")
            m = measure_take(part)
            take = Take(id=f"t{n}", path=str(part), provenance=it["provenance"] if isinstance(it["provenance"], Provenance) else Provenance(**it["provenance"]),
                        onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s, peak_db=m.peak_db, rms_db=m.rms_db, clipped_samples=m.clipped_samples)
            length = it["out"] - it["in"]
            plan.cues.append(Cue(id=f"tl_{n:03d}", track=_ROLE[it["track"]], kind="narration" if it["track"] == "voice" else "music" if it["track"] == "music" else "timeline",
                                 t_in=it["start"], takes=[take], chosen_take=take.id, gain_db=it["gain_db"], status="ready",
                                 fade_in=min(it["fade_in"], length / 2), fade_out=min(it["fade_out"], length / 2)))
        roles = render_roles(plan, tmp_p / "roles")
        out_video = tmp_p / f"mixed{video.suffix or '.mp4'}"
        loud = render_master(plan, tmp_p / "master.wav", target_lufs, video_in=video, out_video=out_video, roles=roles)
        shutil.move(str(out_video), str(video))
    return loud
