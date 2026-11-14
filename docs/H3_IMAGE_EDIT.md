# MiniMax-H3-Image: editing a picture from a written instruction (`engine/comfyui/`)

One open-weights checkpoint that edits an existing picture: you give it the picture and what the
picture should become, and it gives you the new picture. The same checkpoint also does text to
image: the same graph with no picture bound. `qwen_image_21` stays the default art workflow and
H3-Image stays registered once, as `image_edit`; an image job can ask for it by name (see
"Text to image" below).

## What is installed

| File | Size | Where |
|---|---|---|
| `minimax_h3_image_pruned_int8_convrot.safetensors` | 19.54 GiB | `ComfyUI/models/diffusion_models` |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14.61 GiB | `ComfyUI/models/text_encoders` (already there for the H3 video workflows) |
| `minimax_h3_image_vae_fp16.safetensors` | 1.09 GiB | `ComfyUI/models/vae` |

The text encoder is the one the H3 video workflows already use: the copy on disk is byte-identical
to Comfy-Org's H3-Image encoder (sha256 `35a88d51...76f2c6`), so 25.3 GB did not have to be fetched
again.

ComfyUI had to move from 0.43.0 to 0.45.0 (`git pull --ff-only`): 0.43.0 only detects the H3 DiT when
the checkpoint has an audio branch, which the image checkpoint does not, and it had no image VAE.
0.45.0 adds `MiniMaxH3ImageConditioning` and `H3ImageVAE`.

The int8 DiT is the build Comfy-Org publishes and ships in both templates. The bf16 original is
68.65 GB and does not fit this machine; the int8 one is 19.54 GB and does.

The working size is the model's own: the MiniMax API has a `min_generation_area` of 4,194,304
pixels (2048x2048) by default, and a smaller canvas is generated on a larger one at the same aspect
ratio and resized back. The model works at about 4 to 20 megapixels and is best around 16.

## The graph

`engine/comfyui/workflows/minimax_h3_image_edit.api.json` (registered as `minimax_h3_image_edit`,
purpose `image_edit`, sha256 `cb23927552dbfeacc7c945a47afea1097a4a4696207318bf6417224cd428b160`).

Eight nodes: `UNETLoader` -> `MiniMaxH3ImageConditioning` (prompt + the reference pictures) ->
`KSampler` (6 steps, cfg 1, euler/simple) -> `VAEDecode` -> `SaveImage`, with the negative
conditioning from `ConditioningZeroOut`. The checkpoint is distilled, so there is no negative prompt
and no CFG.

It is the flat API form of ComfyUI's official `image_minimax_h3_image_t2i` template, with two
deliberate differences:

- **The in-graph prompt expander is left out.** Comfy-Org's template expands the instruction inside
  the graph with `TextGenerateV2` plus a second text encoder (Qwen3.5 9B, 6.8 GB). PanelFlow writes
  its prompts itself, so the graph must not carry a second text encoder: the expansion happens in
  `engine/comfyui/edit_prompt.py` with the local model that is already installed.
- **The reference pictures go through the conditioning node's own autogrow slots**, the same way the
  Qwen Image 2.1 workflow binds its character lock, so the picture slots can be patched like every
  other reference slot. The node takes up to 100 pictures; PanelFlow binds four.

The model "expects a detailed English description of the whole image" (MiniMax). That is why the
instruction is expanded into a caption before it goes in.

## How an edit runs

1. `POST /api/projects/{id}/comfyui/edit` queues a job (no second submit/poll loop: the same
   `ArtEngine.run` the art workflow uses).
2. `engine/comfyui/service.py::edit_image_operation` reads the picture to edit and scales it to the
   model's working size (about 4 megapixels, the picture's own shape, on the 32-pixel grid). Below
   that the model gives a soft edit, so a small picture is scaled up and the reference carries the
   same detail as the result.
3. `compose_edit_prompt` turns the one-line instruction into the caption the checkpoint was trained
   on: a description of the finished picture that names the pictures it refers to (`<Picture 1>`).
   The local model writes it. If the local model is not reachable the instruction is sent as it is:
   the expansion is a convenience, never a gate.
4. The local model is unloaded before ComfyUI starts: Ollama and the H3 checkpoint do not fit in the
   VRAM together.
5. The result lands in the project as a new asset, with the picture it edited and the caption in its
   provenance.

From the desktop: the image editor modal has **Edit Whole Picture from Instructions (H3 Image)**
next to the inpaint button, for project pictures.

## Measured

RTX 5060 Ti 16 GB, 32 GB RAM, ComfyUI 0.45.0, the picture and the instruction from Comfy-Org's own
edit template (`vintage_yellow_taxi.png`, the yellow taxi on the street).

| Step | Result |
|---|---|
| Preflight | ready: every node registered, every model present (the DiT, the VAE and the text encoder) |
| The caption (local `qwen3.5:9b`, the picture in, one paragraph out) | 7.9 s; it names `<Picture 1>`, describes the finished picture and says what stays as it was |
| The edit (`ArtEngine.edit`, 6 steps) | 55.9 s for 2720x1536 (3.98 MP), the picture scaled to the working size first |
| Peak VRAM | 15,563 MiB of 16,311 MiB - it fits, with about 750 MiB to spare |
| The whole operation (caption, edit, asset written) | 63.3 s; the result lands as a 2720x1536 PNG of 5.16 MB with its sha256 |
| What came out | the yellow taxi became the pastel pink ice-cream truck with the scalloped awning and the glowing service window, in the same side profile at the same curb; the brick building, the blue and orange panels, the red lower wall with the graffiti, the pedestrians and the warm light were kept |

Two runs with the same seed and a different caption (the local model writes a new caption every
time) gave the same instruction followed in two different ways: the first a rounded truck with a
glowing window, the second a van with a scalloped awning. The scene around it was kept in both.

Not measured: other seeds, an edit where a face has to stay the same, the second reference picture
(the instruction refers to another picture).

## Pose and camera transfer

Take the poses, the camera angle and the framing of one picture (often a photograph) and put them on the
characters of an artwork, keeping the artwork's characters, scene and style. The same graph and `ArtEngine.edit`
run it: no second workflow, no new model, no download. `POST /api/projects/{id}/comfyui/edit` with `pose_asset_id`
(a project picture) or `pose_image_data` (an uploaded picture, stored as a `POSE_REFERENCE` asset so the job row stays
small); `prompt` becomes an optional "who plays whom" note. From the desktop: the image editor's **4. Transfer Pose &
Camera** section.

- **The order matters.** `<Picture 1>` is the artwork (kept at its own size, ComfyUI scales it) and `<Picture 2>` is the pose
  picture, scaled to the working size; the result has the pose picture's shape. Tried the other way round (photo as
  `<Picture 1>`) the model drifted to a cleaner anime look and lost the scene; with the artwork first the scene and the
  glow come through, but the photo's beard leaked onto a character until the caption said so.
- **The caption is the whole trick.** `compose_transfer_prompt` (`edit_prompt.py`) has the local vision model look at both
  pictures and write one paragraph that (1) says to keep `<Picture 1>`'s own rendering, (2) pairs each person of
  `<Picture 2>` with one character by role and position, (3) names the traits of the photo person that must not carry over,
  (4) says how many characters there are and that nothing photographic remains. "Replace the men with the characters"
  wording failed: one man stayed photographic and a third figure appeared. Without the model the caption is a plain
  version of the same wording.
- **What is not built:** a switch to use the pose picture as `<Picture 1>`; a project-asset picker for the pose picture
  in the UI (upload from disk only; the API takes an asset id).
- **A second restyle pass makes it worse** (oversharpened, muddy): do not add one.

Measured (2026-11-14, ComfyUI 0.45.0, RTX 5060 Ti 16 GB): the owner's pair, a manhua frame of two fighters in a frozen cave
(1344x768) and a 502x664 stock photograph of a leaping swordsman over a crouching bearded man. Through
`edit_image_operation` with the real local model writing the caption: 1792x2368 results in 91 s for the first run
(caption included; later runs 42-76 s for the edit), peak VRAM 15,734 MiB with the two references, no out-of-memory.
Both seeds gave exactly two manhua characters, no photographic person, the black-coat man leaping with his raised blade
like the swordsman, the cave's bone arch, pillars and glow kept, and the armoured man without the bearded man's face.
Not matched: the crouching man's pose is only approximate (he kneels with the sword forward and faces the viewer where
the photograph has him crouching and looking up at the leaper), the rendering is a little smoother and cleaner than the
original's gritty paint, and on one seed the leaper is cut by the left edge.

Not measured: other pairs, three or more people, a reference with a different number of people than characters, fast
action, two reference photographs, a portrait artwork on a landscape pose picture.

## Text to image

`POST /api/projects/{id}/comfyui/image` with `"workflow_id": "minimax_h3_image_edit"` runs the same
graph through `ArtEngine.generate` with no picture bound. The picture is drawn at the working size
(the requested shape at about 4 megapixels, `h3_edit_size`) and resized to the size that was asked
for; the local model is unloaded first. `refine` is refused (it is built on Qwen). The AI Game Studio
selects it as its image model (`studio/providers.py::H3Image`).

Measured once (2026-11-13, through the studio's provider, 1344x768 asked, 2720x1536 drawn, seed
2026): 51.4 s, peak VRAM 15,512 MiB; the same prompt and seed on Qwen Image 2.1 took 15.3 s. For a
"hand-painted 2D game environment" prompt H3-Image gave a painted picture and Qwen a photographic
one; H3-Image added a string of pennant flags the prompt did not ask for.

Not measured: other prompts and seeds, a character picture, reference pictures on a text to image
job (the character lock was only measured on Qwen), the studio's tile and parallax pipelines on
H3-Image pictures.

## Known limits

- The caption comes from the local 9B model. Comfy-Org's template expands it with Qwen3.5 9B W4A8
  (6.8 GB) inside the graph, and MiniMax's own expander is Qwen3.8-27B FP4 (17.9 GB); PanelFlow
  uses neither, so the caption is rougher than theirs.
- One picture is edited at a time; the extra reference pictures the instruction may refer to are
  passed to the model but are not resized by PanelFlow (ComfyUI scales them itself).
- The picture being edited is scaled to about 4 megapixels, so the result is not the source
  resolution. The model's own working range is about 4 to 20 megapixels, and it is best around
  16; 4 was picked to keep the run inside a 16 GB card.
- The edit is queued as a job and lands as a new asset; it is not wired into Original Stories, the
  storyboard or the character vault yet.
