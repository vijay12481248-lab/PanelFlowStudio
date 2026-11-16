"""Making new sounds for the library with the Audio Studio's existing local sources: speech (Kokoro / Qwen3-TTS), music (ACE-Step), effects
(code-made synth, Openverse CC0). A failure is raised with the source's own reason; nothing is faked and nothing silently switches source.

Effects come back as candidates to hear first (files under _candidates/); keeping one makes it a sound.
"""
from __future__ import annotations

import json
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from engine.audio.library.store import Sound, SoundStore
from engine.audio.studio.plan import Cue, Provenance, SoundPlan
from engine.audio.studio.sources.narration import NarrationProvider, estimate_seconds

_CAND_TTL_S = 24 * 3600


def _plan(duration: float, allow_cc_by: bool = False) -> SoundPlan:
    return SoundPlan(id="library", video_path="", fps=24.0, duration=duration, allow_cc_by=allow_cc_by)


def _why(providers, cue: Cue) -> str:
    out = []
    for p in providers:
        a = p.availability_for(cue) if hasattr(p, "availability_for") else p.availability()
        out.append(f"{p.name}: {a.reason or 'no match'}")
    return "; ".join(out) or "no source can make this"


def make_voice(store: SoundStore, text: str, voice: str = "", provider: str = "kokoro", speed: float = 1.0, language: str = "English",
               name: str = "", narration: NarrationProvider | None = None) -> Sound:
    text = (text or "").strip()
    if not text:
        raise ValueError("write the words to speak first")
    nar = narration or NarrationProvider()
    cue = Cue(id="lib_" + secrets.token_hex(3), track="dialogue", kind="narration", text=text, voice=voice, provider=provider or "kokoro",
              speed=speed, hints={"language": language})
    with tempfile.TemporaryDirectory(prefix="pf-lib-voice-") as tmp:
        cands = nar.find(cue, Path(tmp), _plan(max(30.0, estimate_seconds(text, speed) * 3)), limit=1)
        if not cands:
            raise RuntimeError(_why([nar], cue))
        c = cands[0]
        return store.create_from_file(Path(c.path), name or text[:48], "voice", c.provenance,
                                      info={"text": text, "voice": voice or c.provenance.author, "provider": cue.provider, "speed": speed, "language": language})


def make_music(store: SoundStore, description: str, seconds: float = 30.0, bpm: int | None = None, key_scale: str | None = None, name: str = "",
               music=None) -> Sound:
    description = (description or "").strip()
    if not description:
        raise ValueError("describe the music first")
    seconds = min(max(float(seconds), 5.0), 240.0)
    if music is None:
        from engine.audio.studio.sources.music import MusicProvider
        music = MusicProvider()
    hints = {k: v for k, v in (("bpm", bpm), ("key_scale", key_scale)) if v}
    cue = Cue(id="lib_" + secrets.token_hex(3), track="music", kind="music", intent=description, t_in=0.0, t_out=seconds, hints=hints)
    with tempfile.TemporaryDirectory(prefix="pf-lib-music-") as tmp:
        cands = music.find(cue, Path(tmp), _plan(seconds), limit=1)
        if not cands:
            raise RuntimeError(_why([music], cue))
        c = cands[0]
        return store.create_from_file(Path(c.path), name or description[:48], "music", c.provenance, info={"description": description, "seconds": seconds, **hints})


def _cand_dir(store: SoundStore) -> Path:
    d = store.root / "_candidates"
    d.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for f in d.glob("*"):   # candidates nobody kept are cleared after a day
        try:
            if now - f.stat().st_mtime > _CAND_TTL_S:
                f.unlink()
        except OSError:
            pass
    return d


def find_effects(store: SoundStore, description: str, kind: str = "whoosh", limit: int = 3, providers: list | None = None, allow_cc_by: bool = False) -> list[dict[str, Any]]:
    """Candidates to hear before keeping one: [{id, label, duration_s, provenance}]. Code-made kinds come from the synth; others from Openverse."""
    if providers is None:
        from engine.audio.studio.sources.openverse import OpenverseProvider
        from engine.audio.studio.sources.synth import SynthProvider
        providers = [SynthProvider(), OpenverseProvider()]
    cue = Cue(id="lib_" + secrets.token_hex(3), track="sfx", kind=kind or "whoosh", intent=(description or kind or "").strip())
    if not cue.intent:
        raise ValueError("describe the sound or pick a kind")
    d = _cand_dir(store)
    with tempfile.TemporaryDirectory(prefix="pf-lib-fx-") as tmp:
        for p in providers:
            cands = p.find(cue, Path(tmp), _plan(30.0, allow_cc_by), limit=max(1, min(int(limit), 6)))
            if not cands:
                continue
            out = []
            for c in cands:
                cid = "cand_" + secrets.token_hex(5)
                src = Path(c.path)
                shutil.copyfile(src, d / f"{cid}{src.suffix.lower() or '.wav'}")
                meta = {"id": cid, "label": c.label or c.id, "file": f"{cid}{src.suffix.lower() or '.wav'}", "kind": cue.kind, "intent": cue.intent,
                        "provenance": c.provenance.model_dump()}
                (d / f"{cid}.json").write_text(json.dumps(meta), encoding="utf-8")
                out.append(meta)
            return out
    raise RuntimeError(_why(providers, cue))


def candidate_file(store: SoundStore, cid: str) -> Path:
    meta = _meta(store, cid)
    return store.root / "_candidates" / meta["file"]


def _meta(store: SoundStore, cid: str) -> dict:
    if not (isinstance(cid, str) and cid.startswith("cand_") and cid[5:].isalnum()):
        raise ValueError("bad candidate id")
    p = store.root / "_candidates" / f"{cid}.json"
    if not p.is_file():
        raise FileNotFoundError(f"candidate {cid} is gone (candidates are kept for a day): search again")
    return json.loads(p.read_text(encoding="utf-8"))


def keep_candidate(store: SoundStore, cid: str, name: str = "") -> Sound:
    meta = _meta(store, cid)
    return store.create_from_file(store.root / "_candidates" / meta["file"], name or meta["intent"][:48] or meta["kind"], "effect",
                                  Provenance(**meta["provenance"]), info={"kind": meta["kind"], "description": meta["intent"]})


_KIND_OF_ROLE = {"dialogue": "voice", "music": "music"}


def sounds_from_plan(store: SoundStore, plan) -> list[dict[str, Any]]:
    """The quick Audio page -> the timeline: every ready cue of a Sound Plan becomes a library sound (its licence and source kept; sent again,
    the same take is reused) and a timeline item at the place the mixer would put it (hit frame minus the take's onset/peak, span, gains, fades)."""
    from engine.audio.studio.place import Placement, placement_for
    existing = {(s.info.get("plan"), s.info.get("take")): s for s in store.list() if s.info.get("plan")}
    tracks = {t.role: t for t in plan.tracks}
    items = []
    for cue in plan.cues:
        take = cue.chosen()
        if cue.status != "ready" or take is None:
            continue
        tr = tracks.get(cue.track)
        if tr is not None and tr.mute:
            continue
        snd = existing.get((plan.id, take.id))
        if snd is None:
            name = (cue.text or cue.intent or cue.kind or cue.id)[:48]
            snd = store.create_from_file(Path(take.path), name, _KIND_OF_ROLE.get(cue.track, "effect"), take.provenance,
                                         info={"plan": plan.id, "cue": cue.id, "take": take.id})
        anchor = take.peak_s if cue.anchor == "peak" else take.onset_s
        pl = placement_for(cue.hit_t, anchor) if cue.hit_t is not None else Placement(cue.t_in, 0.0)
        dur = snd.duration_s
        a = min(pl.trim_s, max(dur - 0.01, 0.0))
        b = min(dur, a + (cue.t_out - cue.t_in)) if cue.t_out is not None else dur
        items.append({"cue_id": cue.id, "sound": snd.id, "version": snd.current, "label": snd.name, "kind": snd.kind, "start": round(pl.start_s, 4),
                      "in": round(a, 4), "out": round(b, 4), "duration": dur, "gain_db": round(cue.gain_db + (tr.gain_db if tr else 0.0), 2),
                      "fade_in": cue.fade_in, "fade_out": cue.fade_out})
    return items
