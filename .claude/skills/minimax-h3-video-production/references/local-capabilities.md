# Local capabilities and limits

## Installed `[verified]` (ComfyUI `E:\VIJAY SEKAR\ComfyUI\models`)
- `diffusion_models`: `minimax_h3_fl2va_pruned_int8_convrot`, `fastvideo_fasth3_8step_v2_pruned_int8_convrot` (8-step distill), `qwen_image_2.1_turbo_int8_convrot` (stills).
- `loras`: `minimax_h3_fl2v_turbo_{4,8}step_*`. `text_encoders`: `qwen3vl_32b_minimax_h3_nvfp4_awq` (H3's encoder, not a judge). `vae`: H3 video VAE (int8), H3 audio VAE (fp32).
- Only VLM: Ollama `qwen3.5:9b` (vision), via `OllamaProvider.analyze_vision` (one image per call: use a contact sheet).
- **Not found** (searched names under `E:\VIJAY SEKAR`): Ref2VA transformer, SAM3 weights, LTX weights, H3 Fun ControlNet weights (`model_patches` empty). ComfyUI nodes/blueprints for them exist; nodes without weights do nothing.
- Hosted-only `[official]`: H3-Context-IR (prompt enhancer) and Regenerate-2K. Paid; no pricing found; not open-sourced. Do not use without the owner's approval.

## Workflows `[verified]` (registered in `engine/comfyui/workflow_registry.json`)
| id | use | slots |
|---|---|---|
| `fastvideo_h3_i2v` | beat animation, 8 steps, block-sparse attention, ~0.4 MP | prompt, seed, reference_image, duration |
| `fastvideo_h3_film_free` | film shot, H3 makes its own sound | same |
| `fastvideo_h3_film_voice` | film shot with an anchored voice (`MiniMaxH3AddGuide`) | + voice_audio |
| `minimax_h3_facerefine_i2v`, `minimax_h3_upscale_2k` | face refine / latent upscale, legacy turbo graphs | prompt, seed, reference_image |
Only `first_frame` is wired in all of them. Frame size is derived from the picture (0.5 MP, multiples of 32). `length` snaps to the 17k+5 grid at 24 fps (`film.snap_frames`): 56, 73, 90, 107, 124 ... frames.

## Timings `[verified]` (Dawn Gate, 158 clips, RTX 5060 Ti)
Median 84 s per clip overall (39-192 frames, median 107). Short silent shots 47-64 s when the GPU was otherwise idle; the same shots took 50-133 s in Phase 1 (varies run to run); 124 frames took ~113 s. Same inputs reproduce the same clip bit for bit (Phase 1). Ollama must be unloaded first (`animate.release_ollama`, done by `make_clips`).

## Nodes `[verified]` from `comfy_extras/nodes_minimax_h3.py`
- `MiniMaxH3ImageToVideo`: text, optional `first_frame` (stretched to canvas) and `last_frame` (cover-cropped). Tooltip: trained range about 124-362 frames; longer is untested.
- `MiniMaxH3AddGuide`: anchor an image, a clip (cropped to 5, 22, 39 ... frames) and/or audio at any `frame_idx` (negative = from the end).
- `MiniMaxH3ReferenceToVideo`: `<Picture i>/<Video k>/<Audio j>` references (needs the Ref2VA checkpoint).

## Official limits `[official]` (hosted API docs; local H3 follows the same model family, not guaranteed identical)
4-15 s, 24 fps, 32 kHz stereo audio, short side 768 by default. Ratios 21:9, 16:9, 4:3, 1:1, 3:4, 9:16. Dialogue stable in 11 languages (Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian, Spanish). Reference mode: <=9 images, <=3 videos, <=3 audios, first/last-frame and reference inputs cannot be mixed. No negative prompt, seed or fps field in the API schema (our local graph has a seed).

## Doc discrepancies to remember `[official]`
FL2VA template writes `Picture 1` without angle brackets while I2VA/L2VA use `<Picture 1>`; `<scenetrans>` and `<cutoff>` are named with no syntax; the guide says avoid "cinematic" yet uses it in its own examples; the Context-IR may add details you did not write.

## Our clips are shorter than the official range `[verified]`
Dawn Gate clips are 39-192 frames (1.6-8 s, median 4.5 s); silent close-ups are 56-73 frames (2.3-3 s), below the official 4 s minimum. Phase 1 tested 124 frames on 6 of those: not better, more invention. Keep them short (`references/regeneration.md`).
