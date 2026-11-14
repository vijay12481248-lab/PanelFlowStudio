"""The prompt MiniMax-H3-Image is given for an edit.

The checkpoint was trained on long captions: a description of the finished picture
that names the pictures it refers to (`<Picture 1>`, `<Picture 2>`). A one-line
instruction leaves the model guessing what to keep and what to change.

Comfy-Org's own template expands the instruction inside the graph, with a second
text encoder (Qwen3.5 9B, 6.8 GB). PanelFlow does not carry a second text encoder
inside the graph - the graph has to stay one text encoder, so the expansion is done
here, with the local model that is already installed and already reads pictures.

If the local model cannot be reached the instruction is sent as it is: a plain edit
is better than no edit. The expansion is a convenience, never a gate.
"""

from __future__ import annotations

import base64
import io
import logging

from PIL import Image

logger = logging.getLogger("panelflow.comfyui.edit_prompt")

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3.5:9b"

# The local model reads the picture at this size: the caption needs the content of the
# picture, not its pixels.
_VISION_LONG_EDGE = 1024

_SYSTEM_PROMPT = """You turn a short image-editing instruction into one vivid paragraph \
that describes the finished picture.

Rules:
- Describe the finished picture, not the change: say what the picture shows after the \
edit, never "the user wants to change" or "replace X with Y".
- Name the picture you were given as <Picture 1>. Any other picture is <Picture 2>, \
<Picture 3> and so on.
- Keep everything the instruction does not touch exactly as it is in <Picture 1>: the \
same person, same face, same clothes, same colours, same framing, same style.
- Make the change concrete: what the new thing looks like, where it sits, the light on \
it, the materials, the shadows.
- One paragraph of plain text. No headings, no bullet points, no preamble, no notes.

Example of the shape of the answer:
"The narrow street of <Picture 1> is now lit by a low orange sunset instead of daylight, \
with long shadows running across the wet asphalt between the parked vans, while the \
red-brick corner shop and its blue awning stay exactly where they were." """


def _vision_bytes(picture: bytes) -> bytes:
    """The picture the local model reads: a copy small enough to send quickly."""
    with Image.open(io.BytesIO(picture)) as image:
        image = image.convert("RGB")
        longest = max(image.size)
        if longest > _VISION_LONG_EDGE:
            scale = _VISION_LONG_EDGE / float(longest)
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()


def compose_edit_prompt(instruction: str, reference_picture: bytes, *, timeout_s: float = 240.0) -> str:
    """The caption the edit runs on: the instruction, expanded by the local model.

    The instruction is returned unchanged when the local model is not reachable or
    answers with nothing useful.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return instruction
    try:
        import httpx

        payload = {
            "model": OLLAMA_MODEL,
            "system": _SYSTEM_PROMPT,
            "prompt": f"The picture to edit is <Picture 1>.\nThe editing instruction: {instruction}",
            "images": [base64.b64encode(_vision_bytes(reference_picture)).decode("ascii")],
            "stream": False,
            "think": False,
            "thinking": False,
            "options": {"temperature": 0.2, "num_predict": 700, "num_ctx": 8192},
        }
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(f"{OLLAMA_ENDPOINT}/api/generate", json=payload)
            response.raise_for_status()
            body = response.json()
        text = str(body.get("response") or "").strip()
    except Exception as exc:  # the local model is optional: the edit runs without it
        logger.info("Edit prompt expansion skipped (%s); the instruction is sent as it is", exc)
        return instruction
    if len(text) < 20:
        return instruction
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text or instruction


_TRANSFER_SYSTEM_PROMPT = """You write the instruction for an image model that redraws <Picture 1> \
so its characters take the pose and camera of <Picture 2>.

<Picture 1> is the artwork to keep: its characters, its scene, its lighting and its rendering style.
<Picture 2> is only a pose and camera reference (often a photograph). Its people, faces, beards, \
hair, clothes and background must NOT appear in the result.

Write ONE paragraph of plain text, no headings, no bullet points, no notes. It must:
1. Start with: "Redraw <Picture 1> in exactly its own rendering, line work, shading, textures and colour \
palette, but change the composition so it follows <Picture 2>: the same camera angle, framing and \
placement of the figures, the same body poses."
2. Count the people in <Picture 2> and pair each with one character of <Picture 1>, by role and position \
(for example "On the left, in mid-air, <character from Picture 1> leaps ... exactly like the leaping man of \
<Picture 2>"). Describe each character's face, hair, outfit and weapon as they look in <Picture 1>, and \
describe the body pose as it is in <Picture 2>.
3. For every character, name in a few words the traits of its <Picture 2> partner that must not carry over \
(for example "clean-shaven, nothing of the bearded man's face").
4. End by saying there are exactly that many characters, nothing photographic remains, and the scene, \
lighting, glow and style of <Picture 1> are kept."""


def compose_transfer_prompt(
    character_picture: bytes, pose_picture: bytes, hint: str = "", *, timeout_s: float = 300.0,
) -> str:
    """The caption for a pose and camera transfer: `character_picture` is <Picture 1>, `pose_picture` is <Picture 2>.

    The local model looks at both pictures. When it is not reachable a plain instruction
    is returned (no character descriptions), which still follows the same wording.
    """
    hint = (hint or "").strip()
    plain = (
        "Redraw <Picture 1> in exactly its own rendering, line work, shading, textures and colour palette, but change the "
        "composition so it follows <Picture 2>: the same camera angle, framing and placement of the figures, the same body "
        "poses, each figure of <Picture 2> played by one character of <Picture 1>. Nothing photographic remains: no faces, "
        "beards, clothes or background of <Picture 2>. The scene, lighting, glow and style of <Picture 1> are kept."
    )
    if hint:
        plain += f" {hint}"
    try:
        import httpx

        payload = {
            "model": OLLAMA_MODEL,
            "system": _TRANSFER_SYSTEM_PROMPT,
            "prompt": "The first picture is <Picture 1>, the second is <Picture 2>."
                      + (f"\nWho plays whom, from the user: {hint}" if hint else ""),
            "images": [base64.b64encode(_vision_bytes(p)).decode("ascii") for p in (character_picture, pose_picture)],
            "stream": False,
            "think": False,
            "thinking": False,
            "options": {"temperature": 0.2, "num_predict": 900, "num_ctx": 8192},
        }
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(f"{OLLAMA_ENDPOINT}/api/generate", json=payload)
            response.raise_for_status()
            text = str(response.json().get("response") or "").strip()
    except Exception as exc:
        logger.info("Transfer prompt expansion skipped (%s); the plain instruction is sent", exc)
        return plain
    # The model must name both pictures; otherwise its paragraph cannot steer the edit.
    if len(text) < 80 or "<Picture 1>" not in text or "<Picture 2>" not in text:
        return plain
    return text.strip("`\n ")


def release_local_model() -> None:
    """Unload the local model so ComfyUI has the VRAM: they do not fit together.

    Ollama loads it again on the next request, so this costs nothing but a moment.
    The models are the ones PanelFlow's own provider knows about; the endpoint and the
    fallback model are the ones this module talks to.
    """
    endpoint = OLLAMA_ENDPOINT
    models = {OLLAMA_MODEL}
    try:
        from engine.llm.registry import llm_registry

        provider = llm_registry.get_ollama_provider()
        endpoint = provider.endpoint_url
        models |= {provider.vision_model, provider.text_model, provider.reasoning_model, provider.narration_model}
    except Exception:
        pass
    try:
        import httpx

        with httpx.Client(timeout=20.0) as client:
            for model in {m for m in models if m}:
                client.post(f"{endpoint}/api/generate", json={"model": model, "keep_alive": 0})
    except Exception:
        pass
