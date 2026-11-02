# Original Story Studio - plan

Goal: PanelFlow writes an **original** story, draws it as manga panels with a local image model, lettered by us, then
reuses the existing narration, motion, render and packaging pipeline to publish a long video plus Shorts. The same
story is also exported as a manga chapter (pages). Everything is the user's own work: no source-rights problem.

## What exists (reuse)

| Need | Existing | State |
|---|---|---|
| Image generation | `engine/comfyui` (client, approved-workflow registry, job service), `ComfyImageScreen` | Code only. **ComfyUI is not installed or running** and none of the registry's models (`longcat_image`, `qwen_2.5_vl_7b_fp8`, `ae`) are on disk. No `diffusers`. |
| GPU | RTX 5060 Ti 16 GB, torch 2.14+cu130 works | Enough for SDXL or Flux-fp8 in ComfyUI; Blackwell needs a current torch (already there). |
| Story/characters | `SeriesBible` store (`engine/narration/bible`), narration compiler (`ChapterInputs` = panels + dialogue) | Consumes panel images + dialogue text, so generated panels can enter as if OCR'd. |
| Narration/TTS/music/render/packaging/queue | narration compiler, Kokoro, `engine/audio`, `engine/render`, packaging router, `JobManager` | Working on real manga (acceptance runs) and the anime review workflow. |
| LLM | Ollama `qwen3.5:9b` (text + vision) | Used for the anime review; adequate for outlines, weaker for long coherent plots. |

## Existing problems to solve first

1. **No image engine on disk.** Blocker for everything visual. Needs ComfyUI + a checkpoint (multi-GB download, licence check).
2. **Character consistency.** The hardest part: the same face/outfit across 30+ panels. Needs per-character reference
   sheet + IP-Adapter/LoRA or consistent-seed tricks, and an automatic check (vision model compares each panel to the sheet).
3. **No text in images.** Diffusion models cannot letter. Speech balloons and SFX must be drawn by us (we know the text, so
   this is deterministic) - a new lettering step.
4. **Panel layout.** Models output single images, not pages. We generate panels one by one at set aspect ratios and compose
   pages from layout templates (for the manga export); the video uses panels directly.
5. **Story quality.** A 9B model drifts over long plots. Use the sectioned approach that fixed the anime script:
   premise -> series bible -> episode outline -> scene list -> panel list, each step small and validated.
6. **Throughput.** ~20-60 s per SDXL panel; a 40-panel episode is 15-40 min of GPU time. Must queue, cache and resume.
7. **Fact-check does not apply** (fiction) but a *continuity check* does (names, ages, places, who knows what).
8. **Platform risk.** YouTube "inauthentic/mass-produced content" policy and the synthetic-media label: a human must
   approve scripts and keep stories distinct. Pure AI art is probably not copyrightable, so "no one else can claim it" is
   true, but neither may you be able to enforce rights. Model licence must allow commercial use.

## Architecture

New package `engine/original/`:

- `premise.py`  genre preset (bedtime / horror / mystery / fantasy) + hook -> premise, tone, length.
- `bible.py`    characters (name, age, look prompt, voice), locations, rules; writes into the existing `SeriesBible`.
- `outline.py`  episode outline -> scenes -> panel script `[{panel_id, shot, camera, action, dialogue[], sfx[], caption}]`.
- `art.py`      panel prompt builder (character look + shot + style lock) -> ComfyUI job per panel; seed + prompt stored.
- `consistency.py` vision-model check of each panel vs character sheet; regenerate up to N times; flag the rest.
- `lettering.py` draw balloons/captions/SFX onto panels (Pillow, real fonts) for the manga export; the video keeps
  clean panels and burned captions instead.
- `compose.py`  manga page layouts (1-5 panels) -> page PNG/PDF.
- `project.py`  create a normal PanelFlow project (pages, panels, dialogue as OCR) so narration/motion/render/packaging
  run unchanged. Rights status: `USER_OWNED`.
- API `/api/original/...`, a "New Original Story" screen, jobs through `JobManager`.

Data contracts (JSON in the project workspace): `premise.json`, `bible.json`, `outline.json`, `panels.json`
(every panel: prompt, seed, image path, check result), `pages.json`.

## Milestones (each: tests + a real end-to-end run + commit, as with Anime Review)

- **S0 Image engine.** Install ComfyUI (portable) + one checkpoint, approve a manga/anime-style workflow in the registry,
  verify `capabilities`, generate and inspect a real panel. *Needs the user's decisions below.*
- **S1 Story engine.** Premise -> bible -> outline -> panel script with validation and a continuity check; real run on a
  bedtime story and a horror story; read the output for quality.
- **S2 Art engine.** Panel prompts + ComfyUI jobs, queue/cache/resume; character sheets; consistency check; measure
  how often the same character is recognisably the same.
- **S3 Video from panels.** Build the project, run existing narration + motion + render; verify sync and watch the video.
- **S4 Lettering + manga export.** Balloons/SFX, page layouts, PDF chapter.
- **S5 Shorts.** 9:16 re-render of the best 30-60 s from the timeline with hook caption (also useful for Anime Review).
- **S6 Series + channel automation.** Series bible persists across episodes, channel presets, daily queue, packaging,
  desktop screen. (YouTube upload/analytics, comments assistant are the separate M7+ items.)

## Decisions needed from the user

1. **Image model.** Recommended: SDXL-based anime/manga checkpoint with an OpenRAIL++/permissive licence, or FLUX.1
   schnell (Apache-2.0, ~12 GB, fits 16 GB in fp8, better prompt following, weaker "manga" look without a LoRA).
   Downloads are 6-24 GB; I will not download without approval.
2. **Style.** Black-and-white manga or colour webtoon/anime stills (colour is far easier to keep consistent and looks better as video).
3. **First genre/channel.** Bedtime and horror are the cheapest to make consistent (few characters, simple settings).

## Verification rules

Real generated images and a real rendered video are inspected at every milestone; consistency and story quality are
judged by reading/looking, not by passing tests alone. Anything not verified is listed in the milestone notes.

## S0 result (2026-11-02): image engine installed and verified

- ComfyUI 0.43.0 cloned to `E:\VIJAY SEKAR\ComfyUI` (outside the repo, GPL-3.0) with its own venv (torch 2.14.1+cu130);
  start it with `venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188`.
- Checkpoint `animagine-xl-4.0.safetensors` (6.94 GB, CreativeML Open RAIL++-M, commercial use allowed) in
  `ComfyUI\models\checkpoints`.
- New approved workflow `anime_sdxl` (SDXL, euler_ancestral, 28 steps, cfg 5) bundled at
  `engine/comfyui/workflows/anime_sdxl.api.json` and registered with its checksum; `api_workflow_root()` now falls back
  to the bundled folder.
- PanelFlow discovers installed models through `<PANELFLOW_COMFYUI_WORKFLOW_DIR>/../models`, so set
  `PANELFLOW_COMFYUI_WORKFLOW_DIR=E:\VIJAY SEKAR\ComfyUI\workflow` for the engine (the empty `workflow` folder exists).
  With it set, preflight reports `ready: true`; without it the model shows as missing.
- Real check: one 832x1216 panel (silver-haired girl, candle, dark hallway) generated through the approved workflow in
  30.5 s on the RTX 5060 Ti; sharp, correct anime style, prompt followed except the requested "scared" expression
  (she smiles) - expression control needs work in S2, and prompts must keep characters clearly adult or explicitly
  not child-like in suggestive framing; for kids' bedtime content use child-safe tags and review every image.
- Not verified yet: generation through the `JobManager`/`/api/comfyui` job path, consistent characters, B&W/manga look.

## S1 result (2026-11-02): story engine

`engine/original/` (`models.py`, `genres.py`, `story.py`) and `POST /api/original/story`, `GET /api/original/story/{slug}`,
`GET /api/original/genres`. Steps: premise -> bible (cast, places, world rules) -> scene outline -> panel script per scene,
one small LLM call each, with deterministic validation and retries that name the concrete problems. Panels carry shot,
angle, characters, a visual `action` for the art model, dialogue (<=2 lines, <=18 words), a narrator `caption` (the storyteller
voice that carries the video) and SFX. Genres: bedtime, horror, mystery, fantasy (tone, structure, length, art style tags,
forbidden words; bedtime is child-safe: child protagonist, no antagonist, no gore/scary words).

Real runs with local `qwen3.5:9b` (about 4 minutes each):
- **Bedtime** ("a small child who cannot sleep"): 35 panels, ~8.8 min of narration, child protagonist, gentle arc.
- **Horror** ("an old lighthouse keeper's last night shift"): 40 panels, ~8.3 min, atmospheric, no gore.

What the real runs broke, and the fixes: hyphenated/odd ids and `age_group` words ("kid", "ageless") -> normalised, not failed;
no or two protagonists -> repaired; characters named "They"/"It"/"protagonist" -> rejected (proper name required);
ids drifting from names ("fenrir" for "Mist-Walker") -> id now derived from the name; the first bedtime draft had an adult
protagonist and terrifying wording (nightmare, panic, sweat) -> child protagonist enforced, scary words forbidden for
bedtime; only 175 words for 35 panels (1.2 min) -> every panel needs a 25-45 word storyteller caption (15-35 for horror);
a real term ("Fresnel lens") looked like an invented name -> soft warning after two retries.

Not verified / known weak: stories are coherent but generic; repeated beats appear (two near-identical "tossing and turning"
panels); the model sometimes confuses camera terms with places; the `unknown names` checks are lexical, so invented
*events* are not caught (fiction has no ground truth; a human must read the story); mystery/fantasy not run; no
continuity check of facts across scenes beyond names and cast.

S1 reliability note: on a fresh idea ("a sleepy fox who collects lullabies") the first two attempts failed validation after
retries (a character `look` written as a sentence, mild words like "trapped" in the bedtime forbidden list, panels that
included a character not listed in the scene). Rules were relaxed where they were stricter than needed (look: 4 tags or 8
words; panels may use any bible character; the scary-word list is shorter) and the third run produced a 28-panel, ~7.1 min
story. Expect an occasional failed job with this local model; the job layer (S6) should retry automatically.
