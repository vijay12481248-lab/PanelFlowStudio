"""One long H3 video from a chain of storyboard pictures (Herrgott's H3 Infinite Continuation Suite v1.4, native masked-AV continuation).

Clip 1 runs FL2VA from the first picture to the second; every later clip continues from the previous clip's saved video+audio latent and lands on the next
picture, so motion, framing and sound carry across the joins and the pictures (drawn from the story bible) keep the look from drifting. A final graph decodes the saved
latents, trims the reused head and the frozen tail of each clip and crossfades them into one mp4. Workflows: `herrgott_h3_chain_{start,continue,stitch}` (registered,
checksummed); the submit/poll step is the shared `ArtEngine.run`. Measured and known limits: docs/H3_LONG_VIDEO.md.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine
from engine.comfyui.service import _history_videos
from engine.original import film
from engine.original.models import OriginalStory

START, CONTINUE, STITCH = "herrgott_h3_chain_start", "herrgott_h3_chain_continue", "herrgott_h3_chain_stitch"
SIZE = (960, 544)  # one size for the whole chain: the latent carried between clips cannot change shape
SECONDS = 4.5  # new picture per clip (the continuation samples this much after the protected head)
_BODY = re.compile(r"integrated_multimodal_description: \[Shot 1\] (.*?)\n\noverall_soundscape: (.*?)\n\n", re.S)
_NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,40}$")


@dataclass
class Link:
    index: int  # 1-based clip number
    panel_id: str  # the picture this clip ends on
    last_frame: Path
    prompt: str
    seed: int


def continuation_prompt(story: OriginalStory, panel) -> str:
    """The panel's own system-written motion text, framed as a continuation of the carried context (no per-story wording)."""
    text = film.motion_prompt(story, panel)
    m = _BODY.search(text)
    if not m:  # a multi-shot panel: keep its prompt whole rather than guess at its structure
        return text
    return ("integrated_multimodal_description:\n[Shot 1] Continue directly from the incoming H3 Motion Context. Preserve the same characters, outfits, vehicles, lighting and "
            f"direction of travel; begin new action only after the carried overlap. {m.group(1)} No cut, no duplicate people or vehicles, no motion reset.\n\n"
            f"overall_soundscape:\nContinue the same ambience without an acoustic restart; {m.group(2)}\n\nnon_diegetic_music:\nNo non-diegetic music.")


def plan_chain(story: OriginalStory, ws: Path, panel_ids: list[str], seeds: dict[str, int] | None = None) -> tuple[Path, list[Link], list[str]]:
    """(first picture, one Link per clip, warnings). The pictures must already exist (`film.make_frames`). A change of shot size between neighbouring pictures is the
    main cause of in-clip cuts (measured, docs/H3_LONG_VIDEO.md), so it is reported, not hidden."""
    if len(panel_ids) < 2:
        raise ValueError("a chain needs at least two panels: the first picture and one to land on")
    panels = {p.id: p for p in story.panels}
    unknown = [i for i in panel_ids if i not in panels]
    if unknown:
        raise ValueError(f"unknown panels: {unknown}")
    frames = {i: ws / "film" / "frames" / f"{i}.png" for i in panel_ids}
    missing = [i for i, f in frames.items() if not f.is_file()]
    if missing:
        raise FileNotFoundError(f"no first frame yet for {missing}: run film.make_frames first")
    links = []
    for k, pid in enumerate(panel_ids[1:], 1):
        seed = (seeds or {}).get(pid, int(hashlib.sha256(f"{story.bible.premise.title}|{pid}|chain".encode()).hexdigest()[:12], 16))
        prompt = film.motion_prompt(story, panels[panel_ids[0]]) if k == 1 else continuation_prompt(story, panels[pid])
        links.append(Link(k, pid, frames[pid], prompt, seed))
    warnings = [f"{a} is {panels[a].shot} but {b} is {panels[b].shot}: expect a cut inside the clip between them"
                for a, b in zip(panel_ids, panel_ids[1:]) if panels[a].shot != panels[b].shot]
    return frames[panel_ids[0]], links, warnings


def run_chain(story: OriginalStory, ws: Path, panel_ids: list[str], run_name: str, *, seeds: dict[str, int] | None = None, client: ComfyUIClient | None = None,
              timeout: float = 1500.0, progress=None) -> dict:
    """Render the chain and write `<ws>/film/chain/<run_name>/{clip_N.mp4,chain.mp4}`. Returns {"final": Path, "clips": [Path], "warnings": [...]}.
    Clips are rendered one after another (each needs the previous latent); the latents live in ComfyUI's output folder under h3_continuous/pf_<run_name>.
    Re-running a run_name overwrites its latents and clips (no resume)."""
    if not _NAME.fullmatch(run_name):
        raise ValueError("run_name: lowercase letters, digits and underscores only")
    first, links, warnings = plan_chain(story, ws, panel_ids, seeds)
    client = client or ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    for wid in (START, CONTINUE, STITCH):
        pre = registry.preflight(wid)
        if not pre["ready"]:
            raise RuntimeError(f"ComfyUI workflow {wid} is not ready: nodes {pre['missing_nodes']}, models {pre['missing_models']}")
    engine = ArtEngine(client, registry)
    base = f"h3_continuous/pf_{run_name}"
    out = ws / "film" / "chain" / run_name
    out.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []

    def render(wid: str, values: dict, collect=_history_videos) -> bytes:
        workflow, _ = registry.load(wid)
        raw, _pid, _ref = engine.run(film._apply(workflow, registry.metadata(wid)["patch_slots"], values), timeout=timeout, collect=collect)
        return raw

    for link in links:
        if progress:
            progress((link.index - 1) / (len(links) + 1), f"chain clip {link.index}/{len(links)} -> {link.panel_id}")
        values = {"prompt": link.prompt, "seed": link.seed, "filename_prefix": f"video/pf_{run_name}_clip{link.index}", "width": SIZE[0], "height": SIZE[1], "duration": SECONDS,
                  "last_image": client.upload_image(link.last_frame), "latent_prefix": f"{base}/clip", "clip_index": link.index}
        if link.index == 1:
            values["reference_image"] = client.upload_image(first)
        else:
            values.update(latent_path=base, latent_index=link.index - 1)
        clip = out / f"clip_{link.index}.mp4"
        clip.write_bytes(render(START if link.index == 1 else CONTINUE, values))
        clips.append(clip)
    if progress:
        progress(len(links) / (len(links) + 1), "stitching the chain")
    final = out / "chain.mp4"
    prefix = f"video/pf_{run_name}_stitched"
    final.write_bytes(render(STITCH, {"filename_prefix": prefix, "latent_prefix": f"{base}/clip", "first_clip": 1, "last_clip": len(links)}, collect=_stitched_file))
    return {"final": final, "clips": clips, "warnings": warnings}


def _stitched_file(history: dict, prompt_id: str) -> list[dict[str, str]]:
    """The stitch node saves its mp4 itself and reports only the path (shown through PreviewAny); the path's last two parts are the file in ComfyUI's output folder."""
    record = history.get(prompt_id, history)
    outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
    for out in outputs.values() if isinstance(outputs, dict) else []:
        for text in (out.get("text") or []) if isinstance(out, dict) else []:
            path = Path(str(text).strip().replace("\\", "/"))
            if path.suffix.lower() == ".mp4":
                return [{"filename": path.name, "subfolder": path.parent.name, "type": "output"}]
    return []
