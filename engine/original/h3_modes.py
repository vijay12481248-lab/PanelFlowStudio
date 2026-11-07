"""The other H3 modes the local graph supports besides image-to-video: first+last frame (FL2VA), last frame only (L2VA) and text only (T2VA).

Workflows (registered, checksummed): `fastvideo_h3_film_fl2va`, `fastvideo_h3_film_l2va`, `fastvideo_h3_film_t2va` - the film graph with the `last_frame` input wired,
or with no frame at all (the canvas is then fixed at 960x544, the 0.5 MP size the other film workflows derive from a picture). Prompts follow the official skeleton
(h3-prompt-writing, base guide): an alignment line for FL2VA/L2VA, none for T2VA, then integrated_multimodal_description / overall_soundscape / non_diegetic_music.
FL2VA and L2VA favour ONE shot and say how the last frame is reached.

Ref2VA (reference images -> video) runs through `fastvideo_h3_omniref`: FastVideo's 8-step distilled FastH3 OmniRef checkpoint (`fasth3_omniref_8step_pruned_int8_convrot`, installed
2026-11-07 with the owner's approval, SHA-256 verified) with the `MiniMaxH3ReferenceToVideo` node, euler/simple 8 steps, video shift 12, audio shift 3, VSA attention. Two reference
images are wired (`<Picture 1>` and `<Picture 2>`, the template's identity + location); references and the prompt follow the official six-section Ref2VA format.
"""
from __future__ import annotations

from pathlib import Path

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine
from engine.original.animate import STATIC_CAMERA
from engine.original.film import FPS, _apply, snap_frames

WORKFLOWS = {"i2va": "fastvideo_h3_film_free", "fl2va": "fastvideo_h3_film_fl2va", "l2va": "fastvideo_h3_film_l2va", "t2va": "fastvideo_h3_film_t2va", "ref2va": "fastvideo_h3_omniref", "fl2va_voice": "fastvideo_h3_film_fl2va_voice"}
REF_RETENTION = ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")  # the official retention vocabulary for visible references
T2VA_SIZE = (960, 544)
QUIET = "realistic sound effects that match the action, no speech, no singing."


def clip_seconds(seconds: float) -> float:
    """The length H3 will really render: the 17k+5 frame grid at 24 fps (the S.SS of the alignment line must be this, not the length asked for)."""
    return snap_frames(seconds) / FPS


def _body(action: str, camera: str, tail: str = "") -> str:
    return f"[Shot 1] {action.rstrip('.')}. The camera does {camera}. Single continuous take, smooth natural motion.{tail}"


def _fields(body: str, soundscape: str, music: str) -> str:
    return f"integrated_multimodal_description: {body}\n\noverall_soundscape: {soundscape}\n\nnon_diegetic_music: {music}"


def i2va_prompt(action: str, camera: str = STATIC_CAMERA, soundscape: str = QUIET, music: str = "none") -> str:
    """First frame only (what the film pipeline uses): the picture carries the look, the prompt carries the change."""
    head = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
    return head + _fields(_body(action, camera, " Everything else stays exactly as in the picture."), soundscape, music)


def fl2va_prompt(action: str, seconds: float, camera: str = STATIC_CAMERA, soundscape: str = QUIET, music: str = "none") -> str:
    """First + last frame: Picture 1 is the 0.00 s mark, Picture 2 the end of the clip. `action` describes the path between the two pictures."""
    s = clip_seconds(seconds)
    head = (f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot 1) aligns with the {s:.2f}-second mark of the target video.\n")
    return head + _fields(_body(action, camera, " The last frame is reached by the end of the shot."), soundscape, music)


def l2va_prompt(action: str, seconds: float, camera: str = STATIC_CAMERA, soundscape: str = QUIET, music: str = "none") -> str:
    """Last frame only: the clip converges to the picture. `action` describes the plausible state before it and how it arrives there."""
    s = clip_seconds(seconds)
    head = f"How the reference pictures align with the target video — <Picture 1> (from [Shot 1]) aligns with the {s:.2f}-second mark of the target video.\n"
    return head + _fields(_body(action, camera, " The shot ends exactly on the supplied last frame."), soundscape, music)


def t2va_prompt(scene: str, action: str, camera: str = STATIC_CAMERA, soundscape: str = QUIET, music: str = "none") -> str:
    """Text only: nothing is anchored, so the prompt must carry the look (subject, setting, light, style) as well as the action."""
    return _fields(_body(f"{scene.rstrip('.')}. {action}", camera), soundscape, music)


def ref2va_prompt(subjects: list[tuple[str, int, str, str]], action: str, style: str = "The target video is in a clean anime film style.", camera: str = STATIC_CAMERA,
                  soundscape: str = QUIET, music: str = "none") -> str:
    """Reference to video, the official six sections (ref guide). `subjects` = [(what it is, picture number, retention, what to keep)], e.g.
    ("the girl with copper-red hair, green scarf and brown jacket", 1, "fully_preserved", "face, hair, outfit colours"). Each reference becomes a <Subject n> defined from its
    <Picture n>; a reference that only defines a character, place or style is a Subject, never a standalone Picture entry. `action` is what happens in the one shot."""
    if not subjects or any(r not in REF_RETENTION for _, _, r, _ in subjects):
        raise ValueError(f"subjects need at least one entry with a retention from {REF_RETENTION}")
    defs = "\n".join(f"<Subject {n}> is {what} in <Picture {pic}>." for n, (what, pic, _, _) in enumerate(subjects, 1))
    ret = "\n".join(f"<Subject {n}> (appears in [Shot 1]): {r} - {keep}." for n, (_, _, r, keep) in enumerate(subjects, 1))
    summary = "[reference generation] The target video reuses " + " and ".join(f"<Subject {n}>" for n in range(1, len(subjects) + 1)) + " from the reference pictures in one new shot."
    detail = f"{style}\n{_body(action, camera)}"
    return (f"subject_definitions:\n{defs}\n\nsummary:\n{summary}\n\nretention_analysis:\n{ret}\n\ndetailed_description:\n{detail}\n\n"
            f"overall_soundscape: {soundscape}\n\nnon_diegetic_music: {music}")


def make_clip(mode: str, prompt: str, *, seed: int, seconds: float, first: Path | None = None, last: Path | None = None, refs: list[Path] | None = None, voice: Path | None = None,
              client: ComfyUIClient | None = None, timeout: float = 1500.0, prefix: str = "video/h3_mode", size: tuple[int, int] | None = None) -> bytes:
    """Render one clip in `mode` (i2va | fl2va | l2va | t2va | ref2va) through the registered workflow and the one submit/poll path (`ArtEngine.run`). Returns the mp4 bytes.
    `refs` = 1-2 reference images for ref2va; `voice` = a wav to anchor (fl2va); `size` = (width, height) for t2va / ref2va."""
    from engine.comfyui.service import _history_videos

    wid = WORKFLOWS["fl2va_voice" if mode == "fl2va" and voice else mode]  # `voice`: a wav anchored into the clip (a silent one keeps H3 from inventing speech)
    if (mode == "fl2va" and not (first and last)) or (mode == "l2va" and not last) or (mode == "i2va" and not first) or (mode == "ref2va" and not (refs and len(refs) <= 2)):
        raise ValueError(f"{mode} needs " + {"fl2va": "a first and a last frame", "l2va": "a last frame", "i2va": "a first frame", "ref2va": "1 or 2 reference images"}[mode])
    client = client or ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    pre = registry.preflight(wid)
    if not pre["ready"]:
        raise RuntimeError(f"ComfyUI workflow {wid} is not ready: nodes {pre['missing_nodes']}, models {pre['missing_models']}")
    workflow, _sha = registry.load(wid)
    slots = registry.metadata(wid)["patch_slots"]
    values = {"prompt": prompt, "seed": seed, "filename_prefix": f"{prefix}_{mode}", "duration": seconds}
    if mode == "i2va":
        values["reference_image"] = client.upload_image(first)
    elif mode == "fl2va":
        values["reference_image"], values["last_image"] = client.upload_image(first), client.upload_image(last)
        if voice:
            values["voice_audio"] = client.upload_audio(voice)
    elif mode == "l2va":
        values["last_image"] = client.upload_image(last)
    elif mode == "ref2va":
        values["reference_image"] = client.upload_image(refs[0])
        values["reference_image_b"] = client.upload_image(refs[1] if len(refs) > 1 else refs[0])  # one reference: the second slot repeats it (the graph always wires two)
        values["width"], values["height"] = size or T2VA_SIZE
    else:
        values["width"], values["height"] = size or T2VA_SIZE
    raw, _pid, _ = ArtEngine(client, registry).run(_apply(workflow, slots, values), timeout=timeout, collect=_history_videos)
    return raw
