# PanelFlow Studio - context for coding agents

Local-first desktop app (Tauri + React in `apps/desktop`, Python FastAPI engine in `engine/`) that turns manga/comics, anime
episodes and original stories into narrated YouTube videos. Everything runs on the owner's Windows PC (RTX 5060 Ti 16 GB, 32 GB RAM).

## Run and test
- Python: `.venv\Scripts\python.exe` (Python 3.14). Tests: `.venv\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider`
  (some old suites under `tests/integration` fail to collect for unrelated reasons).
- Desktop type check: `cd apps/desktop && npx tsc --noEmit -p .`
- Engine API on `127.0.0.1:8765`. Tests isolate state through `tests/conftest.py` (temp app-data dir and database).
- Local LLM: Ollama `qwen3.5:9b` (text + vision) on `:11434`. Local-first: never fall back silently to cloud or mock.
- Images: ComfyUI in `E:\VIJAY SEKAR\ComfyUI` (own venv), start with `venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188`;
  set `PANELFLOW_COMFYUI_WORKFLOW_DIR=E:\VIJAY SEKAR\ComfyUI\workflow` so PanelFlow finds the models.
- **One art workflow: `qwen_image_21` (Qwen Image 2.1 Turbo), run only by `engine/comfyui/art.py` (`ArtEngine`).** Original Stories,
  ChronoFlow, the Comfy image screen, YouTube thumbnails and autopilot all call it; do not add a second text-to-image workflow or a
  private submit/poll loop - extend `ArtEngine`. `tests/unit/test_art_engine.py` fails if the registry gains another `text_to_image`
  workflow. The owner's one exception (2026-11-13): an image job may name `minimax_h3_image_edit` as its `workflow_id`; that same registered
  H3-Image graph with no picture bound is text to image (`IMAGE_WORKFLOW_IDS` in `art.py`). Qwen stays the default everywhere; only the AI Game
  Studio's image model picker selects H3-Image. The SDXL entries (`purpose: sdxl_conditioning`, `inpaint`, `matting`) are the legacy substrate of the ControlNet / IP-Adapter /
  inpaint / matting tools, not art workflows. `PANELFLOW_IMAGE_ENGINE` is `qwen` (default) or `sdxl` (for those tools' tests).
- ComfyUI and Ollama together use ~13 GB of VRAM; the job manager holds GPU jobs back when memory is not free (by design).

## What exists (read these docs first)
- `docs/ANIME_REVIEW.md` - anime episode review videos (ingest, rights gate, analysis, script, voice, sync, render, packaging, queue).
- `docs/H3_LONG_VIDEO.md` - videos longer than one H3 clip: `engine/original/chain.py` chains clips between storyboard pictures (measured results and limits).
- `docs/ORIGINAL_STORY_STUDIO.md` - original stories: story engine, shot director, prompt composer, ComfyUI art, image reviewer,
  voiced video, comic pages, series + daily queue, YouTube upload, with the measured results and the known weaknesses of each step.
- `.claude/skills/shorts-reels-production/SKILL.md` - vertical Shorts/Reels (20-32 s, 9:16): concept formula, `tools/reels/` pipeline (Qwen3-TTS, ACE-Step,
  MiniMax-H3-Image, FastH3, ffmpeg), thumbnails, upload copy, gotchas. Any agent making short-form content reads it first (the file is plain Markdown);
  H3 clip prompting lives in `.claude/skills/minimax-h3-video-production/`.
- `docs/ONE_SERVER.md` - one engine (port 8765) serves PanelFlow and ChronoFlow (API + studio UI), and one MCP server (`scripts/run_mcp_server.py`, profiles `all`
  / `creative` / `chronoflow`) drives both. The old standalone ChronoFlow server (7860) and its two extra MCP servers are gone; do not bring them back.
- Code map: `engine/anime/review/` (anime), `engine/original/` (stories), `engine/youtube/` (OAuth + upload), `engine/comfyui/`
  (approved workflows, bundled in `engine/comfyui/workflows/`), `engine/api/routers/{anime_review,original,youtube}.py`,
  desktop screens `AnimeReviewScreen.tsx` and `OriginalStoriesScreen.tsx`. Long jobs run through the durable `JobManager`
  (`engine/jobs`), registered in `engine/jobs/workflow.py`.

## Owner's rules (follow them)
- **Verify on real data.** Diagnose with real output (run it, look at the images/video/audio) before claiming something works or is fixed;
  say plainly what was not verified. Do not grade your own work from tests alone.
- **Generic solutions only.** Fixes must work for any future story/genre/series, never be tuned to one chapter. The system writes the
  prompts (shot director -> prompt composer); do not hand-write prompts per story. The agent guides and corrects the tool.
- **Rights.** Never download or scrape from piracy sites. The rights gate must stay (UNKNOWN is refused); no Content-ID evasion.
  Anime reviews keep clips short and capped, narration is the main content.
- **Publishing.** YouTube uploads are PRIVATE by default; public or scheduled releases need explicit confirmation; "made for kids" is
  the owner's declaration and has no default. Never commit secrets (OAuth client secret and tokens live in the app-data config).
- Downloads of models/files need the owner's approval with the exact file, size and source first.
- Commit per milestone with tests; do not commit unrelated files other work has left in the tree (`git status` shows several).

## Pitfalls
- Shell heredocs can mangle backslashes and `'''`: write non-trivial files with an editor tool, spell regexes as raw strings.
- Windows refuses to replace a file another process holds open: series/episode JSON is written under a lock with retries.
- The 9B local model is a noisy judge: use agreement between independent witnesses (see `engine/original/review.py`), deterministic rules for
  hard requirements, and surface low confidence instead of hiding it.
- Not done yet: Shorts (vertical cut), channel watermark on original-story videos, FLUX face-pinning, real-anime and Japanese-audio runs,
  a listening test of the voices, opening the desktop UI in a real window.
