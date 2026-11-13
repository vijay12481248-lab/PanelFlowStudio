# Local capabilities and limits

## Installed `[verified]` (ComfyUI `E:\VIJAY SEKAR\ComfyUI\models`)
- `diffusion_models`: `minimax_h3_fl2va_pruned_int8_convrot`, `fastvideo_fasth3_8step_v2_pruned_int8_convrot` (8-step distill), `qwen_image_2.1_turbo_int8_convrot` (stills), `minimax_h3_image_pruned_int8_convrot` (H3-Image: edits a picture from a written instruction, 19.54 GiB).
- `loras`: `minimax_h3_fl2v_turbo_{4,8}step_*`. `text_encoders`: `qwen3vl_32b_minimax_h3_nvfp4_awq` (H3's encoder, not a judge; also the H3-Image text encoder, same file). `vae`: H3 video VAE (int8), H3 audio VAE (fp32), H3 image VAE (fp16, 1.09 GiB).
- Only VLM: Ollama `qwen3.5:9b` (vision), via `OllamaProvider.analyze_vision` (one image per call: use a contact sheet).
- **Not found** (searched names under `E:\VIJAY SEKAR`): SAM3 weights, LTX weights, H3 Fun ControlNet weights (`model_patches` empty). Ref2VA: `fasth3_omniref_8step_pruned_int8_convrot.safetensors` (22.21 GB, FastVideo/FastH3-Omni-Comfy) was downloaded 2026-11-07 with the owner's approval; see the Ref2VA note below. ComfyUI nodes/blueprints exist for the rest; nodes without weights do nothing.
- Hosted-only `[official]`: H3-Context-IR (prompt enhancer) and Regenerate-2K. Paid; no pricing found; not open-sourced. Do not use without the owner's approval.
- ComfyUI is at 0.45.0 (upgraded from 0.43.0 for the H3-Image nodes: 0.43.0 only detects the H3 DiT when it has an audio branch, and it had no image VAE).

## H3-Image edits `[verified]`
- Registered as `minimax_h3_image_edit` (purpose `image_edit`, not `text_to_image`: `qwen_image_21` stays the one art workflow). Graph: `engine/comfyui/workflows/minimax_h3_image_edit.api.json`. 6 steps, cfg 1, euler/simple, no negative prompt.
- The picture being edited is scaled to about 4 MP (the model's working size) before it is sent; below that the edit comes out soft. The caption is written by the local `qwen3.5:9b` (the official template expands it in-graph with a 6.8 GB second text encoder, which PanelFlow does not carry), and Ollama is unloaded before ComfyUI runs: they do not fit in the VRAM together.
- Docs: `docs/H3_IMAGE_EDIT.md`.

## Workflows `[verified]` (registered in `engine/comfyui/workflow_registry.json`)
| id | use | slots |
|---|---|---|
| `fastvideo_h3_i2v` | beat animation, 8 steps, block-sparse attention, ~0.4 MP | prompt, seed, reference_image, duration |
| `fastvideo_h3_film_free` | film shot, H3 makes its own sound | same |
| `fastvideo_h3_film_voice` | film shot with an anchored voice (`MiniMaxH3AddGuide`) | + voice_audio |
| `minimax_h3_facerefine_i2v`, `minimax_h3_upscale_2k` | face refine / latent upscale, legacy turbo graphs | prompt, seed, reference_image |
| `minimax_h3_image_edit` | edit a picture from a written instruction (H3-Image, 6 steps, ~4 MP) | prompt, seed, reference_image, reference_image_b/c/d, width, height |
Only `first_frame` is wired in all of them. Frame size is derived from the picture (0.5 MP, multiples of 32). `length` snaps to the 17k+5 grid at 24 fps (`film.snap_frames`): 56, 73, 90, 107, 124 ... frames.

## Timings `[verified]` (Dawn Gate, 158 clips, RTX 5060 Ti)
Median 84 s per clip overall (39-192 frames, median 107). Short silent shots 47-64 s when the GPU was otherwise idle; the same shots took 50-133 s in Phase 1 (varies run to run); 124 frames took ~113 s. Same inputs reproduce the same clip bit for bit (Phase 1). Ollama must be unloaded first (`animate.release_ollama`, done by `make_clips`).

## Nodes `[verified]` from `comfy_extras/nodes_minimax_h3.py`
- `MiniMaxH3ImageConditioning`: H3-Image text to image and editing. Takes the pictures through autogrow `images.image_<n>` slots (`image_1` is the picture being edited) and names them `<Picture 1>`, `<Picture 2>` in the prompt. `width`/`height` of 0 mean "follow image_1" (or 2048 without pictures); the model is tuned for 2048x2048 of area, and Comfy-Org's edit template works at about 4 MP.
- `MiniMaxH3ImageToVideo`: text, optional `first_frame` (stretched to canvas) and `last_frame` (cover-cropped). Tooltip: trained range about 124-362 frames; longer is untested.
- `MiniMaxH3AddGuide`: anchor an image, a clip (cropped to 5, 22, 39 ... frames) and/or audio at any `frame_idx` (negative = from the end).
- `MiniMaxH3ReferenceToVideo`: `<Picture i>/<Video k>/<Audio j>` references; the registered graph `fastvideo_h3_omniref` wires two reference images (identity + location), euler/simple 8 steps, video shift 12, audio shift 3, VSA attention (FastH3 must never run plain block-sparse).

## Official limits `[official]` (hosted API docs; local H3 follows the same model family, not guaranteed identical)
4-15 s, 24 fps, 32 kHz stereo audio, short side 768 by default. Ratios 21:9, 16:9, 4:3, 1:1, 3:4, 9:16. Dialogue stable in 11 languages (Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian, Spanish). Reference mode: <=9 images, <=3 videos, <=3 audios, first/last-frame and reference inputs cannot be mixed. No negative prompt, seed or fps field in the API schema (our local graph has a seed).

## Doc discrepancies to remember `[official]`
FL2VA template writes `Picture 1` without angle brackets while I2VA/L2VA use `<Picture 1>`; `<scenetrans>` and `<cutoff>` are named with no syntax; the guide says avoid "cinematic" yet uses it in its own examples; the Context-IR may add details you did not write.

## Our clips are shorter than the official range `[verified]`
Dawn Gate clips are 39-192 frames (1.6-8 s, median 4.5 s); silent close-ups are 56-73 frames (2.3-3 s), below the official 4 s minimum. Phase 1 tested 124 frames on 6 of those: not better, more invention. Keep them short (`references/regeneration.md`).
