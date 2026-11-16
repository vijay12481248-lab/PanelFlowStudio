"""Sound library MCP tools (the Audio Studio): make, import, edit with versions, undo, split, trash. Thin wrappers over /api/audio/library."""

from __future__ import annotations

from typing import Any

from engine.mcp.client_bridge import bridge
from engine.mcp.registry import registry

_BASE = "/api/audio/library"
_SID = {"type": "string", "description": "The sound id (snd_...) from list_sounds or a make/import tool"}
_KIND = {"type": "string", "enum": ["voice", "music", "effect"]}


def _schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def _body(**kw: Any) -> dict[str, Any]:
    return {k: v for k, v in kw.items() if v is not None}


@registry.tool(name="panelflow_audio_library_list", description="Sounds in the Audio Studio library (name, kind, length, versions, licence). Filter by kind or a word in the name; trash=true lists deleted ones.",
               input_schema=_schema({"kind": _KIND, "q": {"type": "string"}, "trash": {"type": "boolean"}}), domain="chronoflow")
async def list_sounds(kind: str | None = None, q: str | None = None, trash: bool | None = None) -> Any:
    qs = "&".join(f"{k}={v}" for k, v in (("kind", kind), ("q", q), ("trash", str(trash).lower() if trash is not None else None)) if v)
    return await bridge.get(f"{_BASE}/sounds" + (f"?{qs}" if qs else ""))


@registry.tool(name="panelflow_audio_library_ops", description="The edit operations (trim, delete, silence, gain, normalize, fades, speed, pitch, reverse, loop, EQ, reverb, echo, compressor, noise reduction, de-ess, hum, shorten silences) with their parameters, ranges and whether they need a selection.",
               input_schema=_schema({}), domain="chronoflow")
async def ops() -> Any:
    return await bridge.get(f"{_BASE}/ops")


@registry.tool(name="panelflow_audio_library_make_voice", description="Speak text with a local voice (Kokoro on the CPU, or Qwen3-TTS voice cloning on the GPU) and add it to the library as a voice sound.",
               input_schema=_schema({"text": {"type": "string"}, "voice": {"type": "string", "description": "See panelflow_chronoflow_audio_voices"},
                                     "provider": {"type": "string", "enum": ["kokoro", "qwen3_tts"]}, "speed": {"type": "number"}, "language": {"type": "string"}, "name": {"type": "string"}}, ["text"]),
               domain="chronoflow")
async def make_voice(text: str, voice: str | None = None, provider: str | None = None, speed: float | None = None, language: str | None = None, name: str | None = None) -> Any:
    return await bridge.post(f"{_BASE}/sounds/voice", _body(text=text, voice=voice, provider=provider, speed=speed, language=language, name=name), timeout_s=1200)


@registry.tool(name="panelflow_audio_library_make_music", description="Make music with local ACE-Step (MIT) from a description and add it to the library. Takes the GPU; minutes.",
               input_schema=_schema({"description": {"type": "string"}, "seconds": {"type": "number"}, "bpm": {"type": "integer"}, "key_scale": {"type": "string"}, "name": {"type": "string"}}, ["description"]),
               domain="chronoflow")
async def make_music(description: str, seconds: float | None = None, bpm: int | None = None, key_scale: str | None = None, name: str | None = None) -> Any:
    return await bridge.post(f"{_BASE}/sounds/music", _body(description=description, seconds=seconds, bpm=bpm, key_scale=key_scale, name=name), timeout_s=1800)


@registry.tool(name="panelflow_audio_library_find_effects", description="Candidate sound effects to hear before keeping one: code-made kinds (whoosh, impact, click, pop, ding, riser, drop, noise_bed) or an Openverse CC0 search for any other word.",
               input_schema=_schema({"description": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer"}, "allow_cc_by": {"type": "boolean"}}), domain="chronoflow")
async def find_effects(description: str | None = None, kind: str | None = None, limit: int | None = None, allow_cc_by: bool | None = None) -> Any:
    return await bridge.post(f"{_BASE}/effects/find", _body(description=description, kind=kind, limit=limit, allow_cc_by=allow_cc_by))


@registry.tool(name="panelflow_audio_library_keep_effect", description="Keep one effect candidate (from find_effects) as a library sound.",
               input_schema=_schema({"candidate_id": {"type": "string"}, "name": {"type": "string"}}, ["candidate_id"]), domain="chronoflow")
async def keep_effect(candidate_id: str, name: str | None = None) -> Any:
    return await bridge.post(f"{_BASE}/effects/keep", _body(candidate_id=candidate_id, name=name))


@registry.tool(name="panelflow_audio_library_import", description="Add a sound file from this PC (wav, mp3, m4a, flac, ogg, or the sound track of a video) to the library.",
               input_schema=_schema({"path": {"type": "string"}, "name": {"type": "string"}, "kind": _KIND}, ["path"]), domain="chronoflow")
async def import_file(path: str, name: str | None = None, kind: str | None = None) -> Any:
    return await bridge.post(f"{_BASE}/sounds/import", _body(path=path, name=name, kind=kind))


@registry.tool(name="panelflow_audio_library_edit", description="Apply one edit operation to a sound (see panelflow_audio_library_ops); a, b select a part in seconds. Makes a new version; nothing is overwritten.",
               input_schema=_schema({"sound_id": _SID, "op": {"type": "string"}, "params": {"type": "object"}, "a": {"type": "number"}, "b": {"type": "number"}}, ["sound_id", "op"]),
               domain="chronoflow")
async def edit(sound_id: str, op: str, params: dict | None = None, a: float | None = None, b: float | None = None) -> Any:
    return await bridge.post(f"{_BASE}/sounds/{sound_id}/edit", _body(op=op, params=params or {}, a=a, b=b))


@registry.tool(name="panelflow_audio_library_undo", description="Go back one version of a sound (redo=true goes forward again).",
               input_schema=_schema({"sound_id": _SID, "redo": {"type": "boolean"}}, ["sound_id"]), domain="chronoflow")
async def undo(sound_id: str, redo: bool | None = None) -> Any:
    return await bridge.post(f"{_BASE}/sounds/{sound_id}/{'redo' if redo else 'undo'}")


@registry.tool(name="panelflow_audio_library_split", description="Split a sound at a time: it keeps the part before, the part after becomes a new sound.",
               input_schema=_schema({"sound_id": _SID, "at": {"type": "number"}}, ["sound_id", "at"]), domain="chronoflow")
async def split(sound_id: str, at: float) -> Any:
    return await bridge.post(f"{_BASE}/sounds/{sound_id}/split", {"at": at})


@registry.tool(name="panelflow_audio_library_delete", description="Move a sound to the library trash (restore=true brings it back). Emptying the trash is left to the owner on the page.",
               input_schema=_schema({"sound_id": _SID, "restore": {"type": "boolean"}}, ["sound_id"]), domain="chronoflow")
async def delete(sound_id: str, restore: bool | None = None) -> Any:
    if restore:
        return await bridge.post(f"{_BASE}/sounds/{sound_id}/restore")
    return await bridge.delete(f"{_BASE}/sounds/{sound_id}")
