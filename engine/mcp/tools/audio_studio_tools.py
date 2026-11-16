"""Audio Studio MCP tools: sound plans (cue sheets), sourcing, checks, mix and export. Thin wrappers over /api/audio/studio."""

from __future__ import annotations

from typing import Any

from engine.mcp.client_bridge import bridge
from engine.mcp.registry import registry

_BASE = "/api/audio/studio"
_PLAN = {"type": "string", "description": "The sound plan id from create_plan"}
_MODE = {"type": "string", "enum": ["auto", "ask"], "description": "auto: the engine picks; ask: leave candidates for the owner to pick"}
_LUFS = {"type": "number", "description": "Loudness target in LUFS (default -14, YouTube/Shorts)"}


def _schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def _body(**kw: Any) -> dict[str, Any]:
    return {k: v for k, v in kw.items() if v is not None}


@registry.tool(
    name="panelflow_chronoflow_audio_providers",
    description="Which sound sources are usable right now (Openverse CC0 library, code-synth effects, ACE-Step music) and, for any that is not, why.",
    input_schema=_schema({}), domain="chronoflow")
async def providers() -> dict[str, Any]:
    return await bridge.get(f"{_BASE}/providers")


@registry.tool(
    name="panelflow_chronoflow_audio_create_plan",
    description="Start a sound plan (cue sheet) for a finished video file. Probes fps and duration; uses the video's own audio as dialogue unless dialogue_path is given.",
    input_schema=_schema({"video_path": {"type": "string", "description": "Absolute path of the video"}, "mode": _MODE,
                          "allow_cc_by": {"type": "boolean", "description": "Also accept CC-BY clips (credits are written; default false = CC0 only)"},
                          "dialogue_path": {"type": "string", "description": "Optional separate narration/dialogue audio file"}}, ["video_path"]),
    domain="chronoflow")
async def create_plan(video_path: str, mode: str | None = None, allow_cc_by: bool | None = None, dialogue_path: str | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans", _body(video_path=video_path, mode=mode, allow_cc_by=allow_cc_by, dialogue_path=dialogue_path))


@registry.tool(
    name="panelflow_chronoflow_audio_get_plan",
    description="Read a sound plan: tracks, cues (intent, hit time, status, chosen take, candidates, licence, placement error) and version.",
    input_schema=_schema({"plan_id": _PLAN}, ["plan_id"]), domain="chronoflow")
async def get_plan(plan_id: str) -> dict[str, Any]:
    return await bridge.get(f"{_BASE}/plans/{plan_id}")


@registry.tool(
    name="panelflow_chronoflow_audio_put_plan",
    description=("Edit a sound plan. cues: cue objects to add or change; each is merged over the existing cue with the same id and cues you do not mention are kept, so send only what changed; remove_cues: ids to delete. "
                 "Cue fields: id, track (dialogue|music|sfx|ambience|foley), kind (whoosh, impact, click, pop, ding, riser, drop, noise_bed, music, or any word for a library search), "
                 "intent (plain words describing the sound), hit_t (seconds the sound must land on; snapped to the frame), anchor (onset|peak), t_in, t_out, gain_db, fade_in, fade_out, mode, hints {bpm, key_scale}."),
    input_schema=_schema({"plan_id": _PLAN, "cues": {"type": "array", "items": {"type": "object"}}, "remove_cues": {"type": "array", "items": {"type": "string"}}, "tracks": {"type": "array", "items": {"type": "object"}},
                          "mode": _MODE, "allow_cc_by": {"type": "boolean"}, "dialogue_path": {"type": "string"}, "note": {"type": "string"}}, ["plan_id"]),
    domain="chronoflow")
async def put_plan(plan_id: str, cues: list | None = None, remove_cues: list | None = None, tracks: list | None = None, mode: str | None = None,
                   allow_cc_by: bool | None = None, dialogue_path: str | None = None, note: str | None = None) -> dict[str, Any]:
    return await bridge.put(f"{_BASE}/plans/{plan_id}", _body(cues=cues, remove_cues=remove_cues, tracks=tracks, mode=mode, allow_cc_by=allow_cc_by,
                                                              dialogue_path=dialogue_path, note=note))


@registry.tool(
    name="panelflow_chronoflow_audio_spot",
    description="Find picture cuts in the video and draft cues (one transition whoosh per cut plus underscore). If use_vision is true, analyzes keyframes with Ollama Qwen 3.5 9B vision to draft context-aware scene sounds (footsteps, explosions, rain, impacts).",
    input_schema=_schema({"plan_id": _PLAN, "use_vision": {"type": "boolean", "description": "Inspect keyframes with local vision model"}}, ["plan_id"]), domain="chronoflow")
async def spot(plan_id: str, use_vision: bool | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/spot", _body(use_vision=use_vision))


@registry.tool(
    name="panelflow_chronoflow_audio_import_cue",
    description="Import a local audio file (WAV, MP3, FLAC, OGG) as a candidate take for a cue, measuring its onset and peak and marking the cue ready.",
    input_schema=_schema({"plan_id": _PLAN, "cue_id": {"type": "string"}, "file_path": {"type": "string", "description": "Absolute path to local audio file"}, "label": {"type": "string", "description": "Optional human-readable label"}}, ["plan_id", "cue_id", "file_path"]),
    domain="chronoflow")
async def import_cue(plan_id: str, cue_id: str, file_path: str, label: str | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/cues/{cue_id}/import_file", _body(file_path=file_path, label=label))


@registry.tool(
    name="panelflow_chronoflow_audio_source_cue",
    description=("Find or make the sound for one cue. Music cues use local ACE-Step; other cues try Openverse CC0 recordings first, then code-synth effects. "
                 "auto picks a take and marks the cue ready; ask leaves candidates (status needs_pick) for the owner. A cue no source can serve ends failed with the reason."),
    input_schema=_schema({"plan_id": _PLAN, "cue_id": {"type": "string"}, "mode": _MODE}, ["plan_id", "cue_id"]), domain="chronoflow")
async def source_cue(plan_id: str, cue_id: str, mode: str | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/cues/{cue_id}/source", _body(mode=mode))


@registry.tool(
    name="panelflow_chronoflow_audio_pick",
    description="Choose one of a cue's candidates (after source_cue in ask mode). The cue becomes ready.",
    input_schema=_schema({"plan_id": _PLAN, "cue_id": {"type": "string"}, "candidate_id": {"type": "string"}}, ["plan_id", "cue_id", "candidate_id"]),
    domain="chronoflow")
async def pick(plan_id: str, cue_id: str, candidate_id: str) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/cues/{cue_id}/pick", {"candidate_id": candidate_id})


@registry.tool(
    name="panelflow_chronoflow_audio_loop_cue",
    description="Convert a chosen musical score take into an infinite seamless loop using equal-power phase-aligned crossfading.",
    input_schema=_schema({"plan_id": _PLAN, "cue_id": {"type": "string"}, "crossfade_sec": {"type": "number", "description": "Crossfade blend duration in seconds (default 1.5s)"}}, ["plan_id", "cue_id"]),
    domain="chronoflow")
async def loop_cue(plan_id: str, cue_id: str, crossfade_sec: float | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/cues/{cue_id}/loop", _body(crossfade_sec=crossfade_sec))


@registry.tool(
    name="panelflow_chronoflow_audio_qa",
    description="Check the plan: missing/clipped/silent takes and the rendered placement error (ms between each hit and its frame; over 40 ms is an error). Fix every error before exporting.",
    input_schema=_schema({"plan_id": _PLAN}, ["plan_id"]), domain="chronoflow")
async def qa(plan_id: str) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/qa", {})


@registry.tool(
    name="panelflow_chronoflow_audio_critique",
    description="Acoustically critique a sound plan: inspects spectral mud (200-500 Hz), speech masking (dialogue buried by music/SFX), and transient collisions. If apply_fixes is true, automatically updates the plan with recommended DSP fixes.",
    input_schema=_schema({"plan_id": _PLAN, "apply_fixes": {"type": "boolean", "description": "Automatically apply recommended DSP remediations (HPF, gain, ducking, pan)"}}, ["plan_id"]),
    domain="chronoflow")
async def critique(plan_id: str, apply_fixes: bool | None = None) -> dict[str, Any]:
    res = await bridge.post(f"{_BASE}/plans/{plan_id}/critique", {})
    if apply_fixes and res.get("remediations"):
        rids = [r["id"] for r in res["remediations"]]
        applied_res = await bridge.post(f"{_BASE}/plans/{plan_id}/critique/apply", {"remediation_ids": rids})
        return {"critique": res, "applied": applied_res}
    return res


@registry.tool(
    name="panelflow_chronoflow_audio_mix",
    description="Render a master preview: dialogue + music (ducked under dialogue) + effects, limited and normalised to the loudness target. Returns the file name and measured LUFS / true peak.",
    input_schema=_schema({"plan_id": _PLAN, "target_lufs": _LUFS, "mux": {"type": "boolean", "description": "Also write master.mp4 with the video"}}, ["plan_id"]),
    domain="chronoflow")
async def mix(plan_id: str, target_lufs: float | None = None, mux: bool | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/mix", _body(target_lufs=target_lufs, mux=mux), timeout_s=900.0)


@registry.tool(
    name="panelflow_chronoflow_audio_export",
    description="Deliver: stems (dialogue, music, effects, music+effects), master wav (and mp4 with mux), cue sheet json/csv, credits.txt for CC-BY clips, export.json with loudness and QA findings. Refuses while cues are unfinished unless allow_incomplete.",
    input_schema=_schema({"plan_id": _PLAN, "target_lufs": _LUFS, "mux": {"type": "boolean"}, "allow_incomplete": {"type": "boolean"}}, ["plan_id"]),
    domain="chronoflow")
async def export(plan_id: str, target_lufs: float | None = None, mux: bool | None = None, allow_incomplete: bool | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/export", _body(target_lufs=target_lufs, mux=mux, allow_incomplete=allow_incomplete), timeout_s=900.0)


@registry.tool(
    name="panelflow_chronoflow_audio_voices",
    description="Narration voices you can use: Kokoro voices and the Qwen3-TTS reference voices on disk, and whether a speech model is installed.",
    input_schema=_schema({}), domain="chronoflow")
async def voices() -> dict[str, Any]:
    return await bridge.get(f"{_BASE}/voices")


@registry.tool(
    name="panelflow_chronoflow_audio_script",
    description=("Turn narration text into draft narration cues on the Voice lane. Paragraphs (blank lines) or sentences become lines. mode sequential: back to back from `start` seconds "
                 "(estimated lengths plus `gap`); per_cut: line i starts on picture cut i. Then call source_cue on each vo_NN cue to speak it, and qa to check overruns."),
    input_schema=_schema({"plan_id": _PLAN, "text": {"type": "string"}, "mode": {"type": "string", "enum": ["sequential", "per_cut"]}, "start": {"type": "number"}, "gap": {"type": "number"},
                          "voice": {"type": "string", "description": "A Kokoro voice (af_heart, bm_george ...) or a Qwen3-TTS reference voice (see voices)"},
                          "provider": {"type": "string", "enum": ["kokoro", "qwen3_tts"]}, "speed": {"type": "number"}}, ["plan_id", "text"]), domain="chronoflow")
async def script(plan_id: str, text: str, mode: str | None = None, start: float | None = None, gap: float | None = None, voice: str | None = None,
                 provider: str | None = None, speed: float | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/script", _body(text=text, mode=mode, start=start, gap=gap, voice=voice, provider=provider, speed=speed))


@registry.tool(
    name="panelflow_chronoflow_audio_narration_sample",
    description="Speak a line with a voice to hear it before adding it (nothing is added to the plan). Returns a file under the plan and its length in seconds.",
    input_schema=_schema({"plan_id": _PLAN, "text": {"type": "string"}, "voice": {"type": "string"}, "provider": {"type": "string", "enum": ["kokoro", "qwen3_tts"]}, "speed": {"type": "number"}},
                         ["plan_id", "text"]), domain="chronoflow")
async def narration_sample(plan_id: str, text: str, voice: str | None = None, provider: str | None = None, speed: float | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/narration/sample", _body(text=text, voice=voice, provider=provider, speed=speed))


@registry.tool(
    name="panelflow_chronoflow_audio_add_sound",
    description="Describe one sound and where it goes: creates the cue and sources it in one step (mode ask by default so candidates wait for a pick). track: sfx, ambience, foley or music.",
    input_schema=_schema({"plan_id": _PLAN, "intent": {"type": "string"}, "kind": {"type": "string"}, "track": {"type": "string", "enum": ["music", "sfx", "ambience", "foley"]},
                          "hit_t": {"type": "number"}, "t_in": {"type": "number"}, "t_out": {"type": "number"}, "mode": _MODE}, ["plan_id", "intent"]), domain="chronoflow")
async def add_sound(plan_id: str, intent: str, kind: str | None = None, track: str | None = None, hit_t: float | None = None, t_in: float | None = None,
                    t_out: float | None = None, mode: str | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/add_sound", _body(intent=intent, kind=kind, track=track, hit_t=hit_t, t_in=t_in, t_out=t_out, mode=mode), timeout_s=900.0)


@registry.tool(
    name="panelflow_chronoflow_audio_fix",
    description="Fix problems: re-source cues with a clipped, silent or too loud sound (a different clip), push overrunning narration later. Returns what was fixed and what remains.",
    input_schema=_schema({"plan_id": _PLAN}, ["plan_id"]), domain="chronoflow")
async def fix(plan_id: str) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/fix", {}, timeout_s=900.0)


@registry.tool(
    name="panelflow_chronoflow_audio_master",
    description="Broadcast Loudness Master: normalizes soundtrack to -14 LUFS (YouTube/Streaming) or -23 LUFS (EBU R128 Broadcast) with lookahead true-peak limiting (-1.0 dBFS ceiling) and compliance verification.",
    input_schema=_schema({"plan_id": _PLAN, "standard": {"type": "string", "enum": ["youtube", "ebu_r128", "custom"], "description": "Loudness standard (youtube -14 LUFS, ebu_r128 -23 LUFS)"},
                          "target_lufs": _LUFS, "mux": {"type": "boolean", "description": "Mux finished master audio onto the video"}}, ["plan_id"]),
    domain="chronoflow")
async def master_broadcast(plan_id: str, standard: str | None = None, target_lufs: float | None = None, mux: bool | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/master", _body(standard=standard or "youtube", target_lufs=target_lufs, mux=mux), timeout_s=900.0)


@registry.tool(
    name="panelflow_chronoflow_audio_export_daw",
    description="DAW Timeline Interchange: exports FCPXML (Final Cut Pro / DaVinci Resolve Fairlight), CMX 3600 Audio EDL, and complete stems package (DX, MX, SFX, ME, Master, cuesheets, manifest, and zip archive).",
    input_schema=_schema({"plan_id": _PLAN, "standard": {"type": "string", "enum": ["youtube", "ebu_r128", "custom"]}, "target_lufs": _LUFS,
                          "make_zip": {"type": "boolean", "description": "Create a unified daw_delivery.zip archive"}}, ["plan_id"]),
    domain="chronoflow")
async def export_daw(plan_id: str, standard: str | None = None, target_lufs: float | None = None, make_zip: bool | None = None) -> dict[str, Any]:
    return await bridge.post(f"{_BASE}/plans/{plan_id}/export_daw", _body(standard=standard or "youtube", target_lufs=target_lufs, make_zip=make_zip if make_zip is not None else True), timeout_s=900.0)


@registry.tool(
    name="panelflow_chronoflow_audio_auto_foley",
    description="Analyze visual prompts, action directions, and narration in ChronoFlow storyboard scenes to automatically design and populate multi-track atmospheric soundscapes and foley cues with zero-VRAM procedural synthesis.",
    input_schema=_schema({
        "plan_id": _PLAN,
        "scenes": {"type": "array", "items": {"type": "object"}, "description": "Storyboard scene list with prompt, narration, and duration"},
        "auto_source": {"type": "boolean", "description": "Immediately synthesize and source takes (default: true)"},
    }, ["plan_id", "scenes"]),
    domain="chronoflow",
)
async def auto_foley(plan_id: str, scenes: list[dict[str, Any]], auto_source: bool | None = None) -> dict[str, Any]:
    return await bridge.post(
        f"{_BASE}/plans/{plan_id}/auto_foley",
        _body(scenes=scenes, auto_source=auto_source if auto_source is not None else True),
        timeout_s=300.0,
    )

