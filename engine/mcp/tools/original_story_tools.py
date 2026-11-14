"""Original Story Studio (premise, character art, comic pages, video) MCP tools."""

from __future__ import annotations

from typing import Any
from engine.mcp.registry import registry
from engine.mcp.client_bridge import bridge

LONG_JOB_S = 4 * 3600.0  # story, art and video calls block for many minutes; the bridge default (10 min) would drop the result


@registry.tool(
    name="panelflow_original_list_genres",
    description="List supported original story genres (fantasy, sci-fi, horror, comedy, shonen, romance) with tones and default scene counts.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="original",
)
async def panelflow_original_list_genres() -> dict[str, Any]:
    return await bridge.get("/api/original/genres")


@registry.tool(
    name="panelflow_original_create_story",
    description="Generate premise, character bible, story outline, and panel script with local LLM (qwen3.5:9b).",
    input_schema={
        "type": "object",
        "properties": {
            "genre": {"type": "string", "description": "Story genre (e.g. 'fantasy', 'cyberpunk', 'comedy')"},
            "idea": {"type": "string", "description": "High-level premise or prompt for the story"},
            "scenes": {"type": "integer", "description": "Number of scenes (default: 5, range: 3-14)"},
        },
        "required": ["genre"],
    },
    domain="original",
)
async def panelflow_original_create_story(
    genre: str,
    idea: str = "",
    scenes: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"genre": genre, "idea": idea}
    if scenes:
        payload["scenes"] = scenes
    return await bridge.post("/api/original/story", payload, timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_direct_shots",
    description=(
        "Shot director: splits each panel's narration into beats (<= ~24 words) and writes a structured shot spec per beat "
        "(who is on screen, pose, expression, place, key visuals) so every picture follows the spoken words. "
        "Run this after create_story and BEFORE generate_art; without it art is drawn from the plain panel 'action' text, "
        "with no per-beat review."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_direct_shots(slug: str) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/beats", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_generate_art",
    description="Generate character turnaround sheets and comic panel art with the single PanelFlow art workflow (Qwen Image 2.1 Turbo via ComfyUI). Run panelflow_original_direct_shots first so pictures follow the narration.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug returned by panelflow_original_create_story"},
            "limit": {"type": "integer", "description": "Optional limit on panels to generate"},
            "check": {"type": "boolean", "description": "Run consistency verification check with local vision LLM (default: true)"},
            "refine": {"type": "boolean", "description": "Review each picture, then repair or redraw it (slower, needs check; default false)"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_generate_art(
    slug: str,
    limit: int | None = None,
    check: bool = True,
    refine: bool = False,
) -> dict[str, Any]:
    query_parts = []
    if limit is not None:
        query_parts.append(f"limit={limit}")
    query_parts.append(f"check={str(check).lower()}")
    if refine:
        query_parts.append("refine=true")
    query = f"?{'&'.join(query_parts)}" if query_parts else ""
    return await bridge.post(f"/api/original/story/{slug}/art{query}", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_animate",
    description=(
        "Animate key beats of a story with the fast MiniMax H3 image-to-video workflow (about a minute per ~5 s clip). Run after generate_art and before render_video; "
        "the video step shows each clip in place of its still. Without 'beats' the most active beat of each scene is chosen (about one in five)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
            "beats": {"type": "string", "description": "Optional comma list of beat ids to animate, e.g. p08_1,p11_1"},
            "max_clips": {"type": "integer", "description": "Optional cap on how many beats to animate when 'beats' is not given"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_animate(slug: str, beats: str | None = None, max_clips: int | None = None) -> dict[str, Any]:
    query_parts = []
    if beats:
        query_parts.append(f"beats={beats}")
    if max_clips is not None:
        query_parts.append(f"max_clips={max_clips}")
    query = f"?{'&'.join(query_parts)}" if query_parts else ""
    return await bridge.post(f"/api/original/story/{slug}/animate{query}", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_render_video",
    description="Render a fully voiced, 1080p episode video (every picture shown whole and still - no zoom, pan or shake; speech narration, music, captions) and generate YouTube packaging.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
            "burn_captions": {"type": "boolean", "description": "Burn in stylized subtitle captions (default: true)"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_render_video(
    slug: str,
    burn_captions: bool = True,
) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/video?burn_captions={str(burn_captions).lower()}", timeout_s=LONG_JOB_S)


@registry.tool(
    name="panelflow_original_compose_pages",
    description="Letter the panels (balloons, narrator boxes, SFX) and compose print-ready comic book pages and PDF.",
    input_schema={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The unique story slug"},
        },
        "required": ["slug"],
    },
    domain="original",
)
async def panelflow_original_compose_pages(slug: str) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/pages")


# ------------------------------------------------------------------ animated film: frames -> voiced H3 clips -> score -> master
def _query(**kw: Any) -> str:
    q = "&".join(f"{k}={v}" for k, v in kw.items() if v not in (None, ""))
    return f"?{q}" if q else ""


@registry.tool(
    name="panelflow_original_film_frames",
    description="Film step 1: draw one 16:9 first frame per shot with the single art workflow. Starts a background job; poll panelflow_original_film_job. "
                "'ids' = comma list of shot ids (default all); 'rerolls' = e.g. p003:1,p005:2 to draw a better picture of a shot with a new seed.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}, "ids": {"type": "string"}, "rerolls": {"type": "string"}}, "required": ["slug"]},
    domain="original",
)
async def panelflow_original_film_frames(slug: str, ids: str | None = None, rerolls: str | None = None) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/film/frames{_query(ids=ids, rerolls=rerolls)}")


@registry.tool(
    name="panelflow_original_film_clips",
    description="Film step 2: make one MiniMax H3 clip per shot from its frame. A speaking shot gets its character's own voice anchored into H3, so the mouth is generated to the words (lip sync); "
                "silent shots get H3's own sound effects. Nothing is looped. Minutes per clip; background job. 'seeds' = e.g. p004:7 to retry a shot.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}, "ids": {"type": "string"}, "seeds": {"type": "string"}, "quiet": {"type": "string", "description": "comma list of shots whose sound is anchored to silence (use when H3 invented speech in a silent shot and a new seed did not fix it)"},
                                                  "native_voice": {"type": "boolean", "description": "true = H3 speaks each line itself in a voice described from the character (no TTS, no anchored audio)"}}, "required": ["slug"]},
    domain="original",
)
async def panelflow_original_film_clips(slug: str, ids: str | None = None, seeds: str | None = None, quiet: str | None = None, native_voice: bool = False) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/film/clips{_query(ids=ids, seeds=seeds, quiet=quiet, native_voice=str(native_voice).lower())}")


@registry.tool(
    name="panelflow_original_film_score",
    description="Film step 3: one instrumental local ACE-Step cue per scene, sized to the scene's real length. Unloads ComfyUI and the LLM first. Background job.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
    domain="original",
)
async def panelflow_original_film_score(slug: str) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/film/score")


@registry.tool(
    name="panelflow_original_film_master",
    description="Film step 4: cut all clips in order, mix the score ducked under the clips' sound, normalise loudness, write the 1080p mp4 and SRT captions. Background job.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}, "ids": {"type": "string"}, "music": {"type": "boolean"}, "name": {"type": "string"}}, "required": ["slug"]},
    domain="original",
)
async def panelflow_original_film_master(slug: str, ids: str | None = None, music: bool = True, name: str = "film_master") -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/film/master{_query(ids=ids, music=str(music).lower(), name=name)}")


@registry.tool(
    name="panelflow_original_film_job",
    description="Progress and result of a film job started by one of the panelflow_original_film_* tools (status, progress 0-1, message, result or error).",
    input_schema={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    domain="original",
)
async def panelflow_original_film_job(job_id: str) -> dict[str, Any]:
    return await bridge.get(f"/api/original/film/job/{job_id}")


@registry.tool(
    name="panelflow_original_film_status",
    description="What exists for a film: frames, clips, total seconds, clips measured as too still, the running job, and per-shot detail.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
    domain="original",
)
async def panelflow_original_film_status(slug: str) -> dict[str, Any]:
    return await bridge.get(f"/api/original/story/{slug}/film/status")


@registry.tool(
    name="panelflow_original_clip_eval",
    description="Measured review of one film clip (no score): camera zoom/pan, hard cuts, flicker, still picture, colour drift, audio, each flag with a timestamp and status confirmed|suspected. "
                "camera='static' flags any camera move, 'any' only reports it. It does NOT check identity, objects or prompt match: look at the clip too.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}, "shot": {"type": "string"}, "camera": {"type": "string", "enum": ["static", "any"]}}, "required": ["slug", "shot"]},
    domain="original",
)
async def panelflow_original_clip_eval(slug: str, shot: str, camera: str = "static") -> dict[str, Any]:
    return await bridge.get(f"/api/original/story/{slug}/film/clip/{shot}/eval{_query(camera=camera)}")


@registry.tool(
    name="panelflow_original_clip_improve",
    description="Correction loop for one film clip: evaluate, change ONE thing (static camera, simpler action, wider/new first frame, new seed), regenerate in an isolated workspace, keep the better clip. "
                "Background job (a minute or two per attempt); poll panelflow_original_film_job. The real clip is replaced only with apply=true; read panelflow_original_clip_history first and look at the result.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}, "shot": {"type": "string"}, "attempts": {"type": "integer"}, "camera": {"type": "string", "enum": ["static", "any"]},
                                                  "suspected": {"type": "boolean", "description": "also act on suspected flags (look at the frames first)"}, "apply": {"type": "boolean"},
                                                  "redraw": {"type": "boolean", "description": "allow the first-frame levers (needs ComfyUI art)"}}, "required": ["slug", "shot"]},
    domain="original",
)
async def panelflow_original_clip_improve(slug: str, shot: str, attempts: int = 3, camera: str = "static", suspected: bool = False, apply: bool = False, redraw: bool = True) -> dict[str, Any]:
    return await bridge.post(f"/api/original/story/{slug}/film/clip/{shot}/improve{_query(attempts=attempts, camera=camera, suspected=str(suspected).lower(), apply=str(apply).lower(), redraw=str(redraw).lower())}")


@registry.tool(
    name="panelflow_original_clip_history",
    description="Every correction attempt recorded for a film clip: lever, settings changed, evaluator flags, kept or discarded and why.",
    input_schema={"type": "object", "properties": {"slug": {"type": "string"}, "shot": {"type": "string"}}, "required": ["slug", "shot"]},
    domain="original",
)
async def panelflow_original_clip_history(slug: str, shot: str) -> dict[str, Any]:
    return await bridge.get(f"/api/original/story/{slug}/film/clip/{shot}/history")


@registry.tool(
    name="panelflow_scene_propose",
    description="Scene Director step 1: turn a vague brief ('the hero fights the villain') into a complete scene plan (who stands where, what each body is doing, camera, light, depth) "
                "with proposed defaults and at most 3 questions. Show the summary to the user; they say go or correct a few items (panelflow_scene_correct).",
    input_schema={"type": "object", "properties": {"brief": {"type": "string"}, "scene_type": {"type": "string", "enum": ["fight", "emotion", "concept_art"]}}, "required": ["brief"]},
    domain="original",
)
async def panelflow_scene_propose(brief: str, scene_type: str | None = None) -> dict[str, Any]:
    return await bridge.post("/api/original/scene/propose", {"brief": brief, **({"scene_type": scene_type} if scene_type else {})}, timeout_s=600.0)


@registry.tool(
    name="panelflow_scene_correct",
    description="Scene Director step 2: apply the user's corrections to a plan. Keys are dotted paths: camera.angle (eye_level|low|high|dutch), camera.distance, light.direction, "
                "actors.<id>.action_state, actors.<id>.side, contacts.<actor id>.direction, depth.<layer>, mood, setting. A contradiction (both fighters on one side, a strike aimed away from its target) is refused with the problem, so swapping sides needs contacts.<actor id>.direction swapped in the same call.",
    input_schema={"type": "object", "properties": {"plan": {"type": "object"}, "corrections": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["plan", "corrections"]},
    domain="original",
)
async def panelflow_scene_correct(plan: dict, corrections: dict) -> dict[str, Any]:
    return await bridge.post("/api/original/scene/correct", {"plan": plan, "corrections": corrections})


@registry.tool(
    name="panelflow_scene_generate",
    description="Scene Director step 3: draw the plan with Qwen, check the picture against the plan, redraw what is wrong (up to 3 attempts / 60 s), deliver the best picture with what it still "
                "misses listed. Background job: poll the job id. Look at the picture before telling the user it is good; 'unverified' means the checker could not judge it.",
    input_schema={"type": "object", "properties": {"project_id": {"type": "string"}, "plan": {"type": "object"}, "seed": {"type": "integer"}}, "required": ["project_id", "plan"]},
    domain="original",
)
async def panelflow_scene_generate(project_id: str, plan: dict, seed: int | None = None) -> dict[str, Any]:
    return await bridge.post("/api/original/scene/generate", {"project_id": project_id, "plan": plan, **({"seed": seed} if seed is not None else {})})


@registry.tool(
    name="panelflow_scene_rate",
    description="Record the owner's verdict on a delivered scene picture (good / not good, with a reason when not good: emotion, pose, camera, identity, style, other). "
                "Returns the running summary; the share of 'good' is the measure of whether the Scene Director matches what the owner imagined.",
    input_schema={"type": "object", "properties": {"brief_id": {"type": "string"}, "good": {"type": "boolean"}, "reason": {"type": "string"}, "mode": {"type": "string", "enum": ["raw", "director"]},
                                                  "seconds": {"type": "number"}}, "required": ["brief_id", "good"]},
    domain="original",
)
async def panelflow_scene_rate(brief_id: str, good: bool, reason: str = "", mode: str = "director", seconds: float = 0.0) -> dict[str, Any]:
    return await bridge.post("/api/original/scene/rate", {"brief_id": brief_id, "good": good, "reason": reason, "mode": mode, "seconds": seconds})
