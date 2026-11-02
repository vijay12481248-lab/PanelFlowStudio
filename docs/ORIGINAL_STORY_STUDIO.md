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

## S2 result (2026-11-02): art engine

`engine/original/art.py` + `POST /api/original/story/{slug}/art?limit=&check=`: per story it renders a character sheet
per character, then every panel through the approved `anime_sdxl` ComfyUI workflow (1344x768), storing `art.json`
(prompt hash, seed, attempts, consistency score, missing tags). Reruns reuse any panel whose prompt is unchanged and redo
only edited ones. Prompts repeat each character's exact `look` tags plus shot/angle tags, the location look and the genre
art style; the negative prompt blocks nsfw/text/bubbles. A vision check then confirms the character's core look tags and
a panel scoring below 0.6 is regenerated once with a new seed and the missing tags emphasised `(tag:1.3)`.

Real runs on stored stories (RTX 5060 Ti, ~28 s per image; ~40 s per panel with the check):
- **Fox bedtime story**, 10 panels: the fox is recognisable in every panel by eye; the vision check's core-tag score is
  mean 0.70 (0.5-1.0, one 0.0 on an extreme close-up). Images are clean, colourful, storybook style.
- **Horror story**, 6 panels: atmospheric, dark, the keeper is recognisably the same figure (long white hair, dark coat,
  goggles) in 3 of the 4 panels I inspected; the character sheet shows him with darker, shorter hair.

What the runs broke and the fixes: (1) the first check asked the vision model to match characters by *name* and it answered
with tag names, so every panel scored 0 -> the check is now one call per character with an explicit tag list; (2) it demanded
all 5-8 tags, including the carried item and textures ("salt-crusted hair"), which the 9B vision model cannot confirm (it denied
a clearly visible fox cub) -> only the first 3 core tags (2 for close-ups) are checked; (3) `look` fields that described another
character ("glowing moth companion perched on shoulder") are now rejected and the bible prompt asks for drawable colour-and-shape
tags; (4) retries capped at 2 attempts.

Not solved / honest limits: consistency is a *prompt-tag baseline* - same outfit and species yes, same face no (that needs
IP-Adapter or a LoRA: an extra ~1.5 GB of downloads and a ComfyUI custom node, to be decided in S2b); two characters in one
prompt blend features (a fox grew moth wings); the checker is noisy, so scores are a coarse signal and a human should skim
the contact sheet; the character sheet prompt sometimes draws several copies of the character; the horror run was made before
the drawable-tags prompt change and the new bible prompt itself was not re-run against the LLM; not yet verified through the
`JobManager`/API path (long call, S6 queues it).

## S2b result (2026-11-02): IP-Adapter for consistent faces

Installed (approved, 3.4 GB): `ip-adapter-plus_sdxl_vit-h.safetensors` (848 MB, Apache-2.0) and the CLIP ViT-H image encoder
(`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`, 2.53 GB) from `h94/IP-Adapter`, plus the `ComfyUI_IPAdapter_plus` custom
node (GPL-3.0) in `ComfyUI\custom_nodes` (ComfyUI restarted to load it). New approved workflow `anime_sdxl_ipa`
(`engine/comfyui/workflows/`, registry entry with an optional `reference_image` patch slot; registry/service accept it only
for workflows that declare it). `ComfyRunner` uploads the reference to ComfyUI and uses this workflow whenever a panel
shows a character; the first character on screen is pinned to its sheet, and the reference name is part of the cache key.
Character sheets are now one clean portrait (they double as the reference). If the adapter models or nodes are missing the
runner silently falls back to prompt-only consistency.

Real A/B on the fox story (same 8 panels, same checker):
- prompt-tags only: core-tag score mean **0.70**, ~40 s/panel (frequent regeneration);
- IP-Adapter weight 0.6: **0.96**, all first attempts, ~20 s/panel, but compositions copied the portrait (same pose/framing);
- IP-Adapter weight 0.45, ends at 65% of the steps (shipped): **0.92**, all first attempts, faces clearly the same fox across
  panels (blue eyes, forehead spots, orange fur) with real variety of pose and setting.

Still wrong: panels with two characters (fox + moth) draw several foxes - only one reference is applied, and the second
character is not drawn from its own reference; the pastel style washes out strong genre mood (horror was not re-tested with the
adapter); small "ghost" creatures clutter backgrounds. Next ideas: two-reference regional prompting for two-character panels
(a second IPAdapter node with an attention mask) and re-testing horror.

## S3 result (2026-11-02): video from panels

`engine/original/video.py`, `POST /api/original/story/{slug}/video`. Each panel is voiced by the genre's storyteller
(bedtime `af_heart` at 0.88x, horror `bm_george`, mystery `am_adam`, fantasy `bm_fable`; only voices cached offline are
used) with a distinct voice per character for dialogue; the panel's audio length (frame-aligned, min 3 s, 0.6 s closing
pause) is its length on screen, as in the anime review sync. Rendering: the panel image is cropped to 16:9 and gets a slow
push-in / pan-right / push-out / pan-left (zoompan on a 2x upscale), burned-in captions, fade in/out at the ends, NVENC with
CPU fallback; segments are concatenated and mixed with the music bed, then loudness-normalised to -16 LUFS. Reruns reuse
unchanged voice and segment files (per-panel content hash). `package()` writes title, description with chapters per scene and
an AI-content disclosure, tags and a thumbnail from a close/medium panel.

**Deviation from the plan**: the existing manga project pipeline was not used. It OCRs page images and rewrites narration
from them, while stories here already carry narration and dialogue, so a direct path reusing the Kokoro adapter, caption/SRT
helpers, encoder detection and music bed was smaller and verifiable. Registering generated stories as normal projects
(dashboard, auto-pilot, story editor) is not done.

Real run, fox bedtime story (28 panels, all generated with IP-Adapter, check score mean 0.875, none below threshold):
**6:32 1080p video built in 75 s**, 11776 frames = timeline 392.53 s x 30 fps exactly, -16.1 LUFS (the first mix was -28.6
dB mean, too quiet, hence the normalisation), SRT sidecar, 5 chapters. Frames inspected at 4 points: clean storybook look,
readable captions, correct motion.

Visible problems: the hero fox comes out white/pink in one panel and orange in the others; the two-character panels draw
three foxes and winged foxes (character blending, see S2b); captions are verbose (whole narration is burned in); the same
music bed as the anime review (not genre-specific); voices were not listened to; chapter labels are just the first 7 words of
each scene summary; only one story/genre was rendered; the API route was not exercised and nothing is queued via `JobManager` yet.

## S2c result (2026-11-02): two-character panels

New approved workflow `anime_sdxl_ipa2` (`registry` optional slot `reference_image_b`, fixed 1344x768): two IP-Adapter
nodes chained on the same model, each with an attention mask - the first character's portrait owns the left half of the
frame, the second the right half (SolidMask + MaskComposite). `ComfyRunner` uses it for panels with two characters and the
prompt now says `2others` instead of `multiple others`; cache keys include both reference names; if the workflow or its nodes
are missing it falls back to the single-reference workflow.

Real check on the four fox+moth panels that had produced three foxes and winged foxes: **3 of 4 now show exactly one fox
and one winged girl (Lumina) side by side**, recognisably the same characters as their portraits; the fourth shows the fox
and only a tiny moth (Lumina is shrunk or missing). Vision check mean 0.92, all first attempts, ~20 s/panel.

Limits: the left/right split is a fixed layout (first character left, second right), so compositions with a character in
front of another, or three-character scenes (only the first two are drawn), are not handled; the second character
occasionally disappears; the other panels of the fox video were not regenerated yet.

## S4 result (2026-11-02): lettering and comic pages

`engine/original/lettering.py` (balloons, narrator box, SFX; Comic Sans/Impact with fallbacks) and
`engine/original/pages.py`; `POST /api/original/story/{slug}/pages` writes `pages/page_XXX.png` (1600x2400), `lettered/`
and `comic.pdf`. A cover page (hero art, title, logline, AI-content line) is followed by pages of three full-width lettered
strips each (webtoon-style stacking: landscape art would lose its left/right characters in tall manga cells). Dialogue
balloons sit over the speaker's half of the frame (first character left, second right, matching the two-reference art
layout) with the tail pointing down; two lines of the same speaker stack; the narrator text becomes a cream box at the bottom,
shortened to its first ~22 words (the full 25-45 word storyteller text is for the video); SFX are drawn in yellow Impact with a
dark outline. Missing images are reported, never faked.

Real export of the fox story (28 panels): **11 pages (cover + 10) and a 4 MB PDF in 6.5 s**. Inspected: cover and body
pages read well, balloons are legible and no longer collide after I narrowed their width (the first version let two
balloons touch because the text width ignored the padding), tails point at the speaker's half.

Limits: balloon positions are layout-based, not face-aware (a single centred character with two speakers off-frame gets
tails pointing at empty space, as in one inspected panel); caption boxes cover the bottom of the art; this story contains no
SFX so the SFX drawing is only covered by unit tests; right-to-left manga reading order, black-and-white screentone and
non-stacked page layouts are not done; the fox art in this export predates the two-character fix.
