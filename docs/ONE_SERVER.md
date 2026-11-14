# One engine, one MCP server

PanelFlow Studio and its video studio, ChronoFlow, are one application, so they run on **one engine process** (port 8765) and are
driven through **one MCP server**. Nothing else needs to be started besides ComfyUI and Ollama.

| What | How it runs |
|---|---|
| The engine | `run_engine.py` (the desktop app, `launch_panelflow.ps1` and Tauri all start it). Serves the PanelFlow API, the **ChronoFlow API** (`/api/chronoflow/...`) and the **ChronoFlow studio UI** (`/chronoflow/ui`). |
| The MCP server | `scripts/run_mcp_server.py` (stdio, started by the AI client). Every tool is a thin wrapper over the engine's HTTP API, so the engine must be running for tools to work. |
| ChronoFlow in the desktop app | `ChronoFlowScreen` shows `http://127.0.0.1:8765/chronoflow/ui` in an iframe. |

## History: why there were five servers

ChronoFlow began as its own product (its own web server on port 7860 and its own MCP). It was folded into the engine on
2026-11-05, but the old pieces stayed, so there were three stdio MCP servers (PanelFlow's 96 tools, a "creative" subset of the same
tool list, and ChronoFlow's 8) and two web servers (the engine and the standalone ChronoFlow server). The standalone server and the
engine each started their own job supervisor and both wrote the same `engine/chronoflow/vault/jobs.json` and `characters.json`.

## The MCP server and its profiles

One server, `panelflow-studio-mcp`. A client that wants only a slice asks for a profile; a tool outside it is neither listed nor
callable.

| Profile | Tools | For |
|---|---|---|
| `all` (default) | 96 | everything |
| `creative` | 20 | the creative agents and the LLM settings (exactly what the old creative server exposed) |
| `chronoflow` | 14 | the ChronoFlow video studio only |

```
python scripts/run_mcp_server.py                       # all tools
python scripts/run_mcp_server.py --profile creative
python scripts/run_mcp_server.py --profile chronoflow
```

`PANELFLOW_MCP_PROFILE` does the same from the environment. In a client config (see `mcp_panelflow.json`) one entry is enough;
add `"args": [".../run_mcp_server.py", "--profile", "chronoflow"]` for a lean one.

Added: `panelflow_chronoflow_cancel_job`. The old ChronoFlow MCP could cancel a ChronoFlow job, the main server could not
(`panelflow_cancel_job` reaches the durable job manager, not ChronoFlow's supervisor).

Removed: `engine/chronoflow/mcp_server.py` (every tool is covered by a `panelflow_chronoflow_*` tool; nothing referenced it),
`engine/mcp/creative_mcp_server.py` and `run_creative_mcp.py` (now `--profile creative`).

## What moved from the port 7860 server into the engine

Only what the ChronoFlow UI actually calls and the engine lacked:

| Route | Where |
|---|---|
| Magic Brush and range editing: `/api/chronoflow/nle/{upload_ref, frame/generate, range/auto_prompt, range/generate, range/apply}` | `engine/api/routers/chronoflow_nle.py` |
| Story workbench in ChronoFlow's Story tab: `/api/original_stories/{list, {slug}/workbench, panel, audio, agent_action, approve, reroll, open}` | `engine/api/routers/chronoflow_stories.py` (a thin adapter over `engine.api.routers.original`; the somatic table is `engine/chronoflow/somatic.py`) |
| "Launch ComfyUI" button: `/api/chronoflow/dependencies/launch_comfyui` | `engine/api/routers/chronoflow.py` |

Removed: `engine/chronoflow/server.py`, `run_studio.py`, the `7860` probing in `ChronoFlowScreen.tsx` and the `7860` entries in the
allowed local origins. Not carried over: the standalone server's unused `frame/inpaint` and `frame/apply` routes and its `/api/creative/*`
routes (the UI inpaints through `/api/chronoflow/inpaint_image`; the creative tools live in the engine's `creative` router).

## Things the move fixed (they were wrong in the old server)

- `frame/generate` called `ArtEngine.generate_image`, which does not exist, so it always failed. It now calls `ArtEngine.generate` (Qwen
  Image 2.1) and passes the chosen reference picture, which the old code read and ignored.
- `upload_ref` joined the client's file name to the input folder as it came (path traversal) and copied any path or downloaded any URL
  it was given. It now keeps a bare file name, accepts a data URL or a picture already in the media folders, and checks it is a picture.
- A story panel id and a clip name are reduced to safe names before they touch the disk.
- `range/generate` used the sample picture `zombie_survivor_anchor.jpg` when no frame could be found; it now says there is no frame to start from.
- `range/generate` rendered at 1344 x 768 unless the job knew its size, which cannot be joined to a portrait master (ffmpeg's concat
  needs equal sizes). It now uses the job's size, else the master's.

## Behaviour to know

- With no `job_id`, the range routes work on the **newest master video** in `output/chronoflow`, as the old server did. Pass the job id.
- Several ChronoFlow unit tests write jobs into the real `engine/chronoflow/vault/jobs.json` (for example `test_chronoflow_api.py`'s
  "Cinematic breach" scene). Run them, then `git checkout` the vault files.

## Checked

Unit tests: `tests/unit/test_chronoflow_nle.py` (19), `test_mcp_profiles.py` (18), plus the existing ChronoFlow, MCP, security and
story-workbench suites (159 together). On the real running engine: the studio UI loads, `launch_comfyui`, the story list (66 stories),
a workbench and its agent action, path traversal refused, a data-URL upload under a safe name, a bad upload refused; **real Magic
Brush frame generation** (a 1024 x 576 picture in 9 s), a **real range clip** from Fast H3 at the master's own 768 x 1344, the
**real splice** into a copy of a master (62.04 s to 62.38 s, as expected) and a real local-model `auto_prompt` from a real frame.
The real MCP server over stdio: 96 / 20 / 14 tools for the three profiles and for the environment variable, a live
`panelflow_chronoflow_status` and `panelflow_chronoflow_cancel_job`, an out-of-profile tool refused, a bad profile exits with an error.

**Not checked:** the ChronoFlow UI clicked through in the desktop window (the routes are verified, the screen was only type-checked);
the Tauri build; `range/apply` on a real job's master (done on a copy, so your masters stay untouched).

The full unit suite has 35 failures that do not involve this change (a missing `AudioService.synthesize_mapped_narration`, a missing
`project_925_snapshot.json` fixture, NVENC "could not open encoder" while ComfyUI holds the GPU, job-timing races) plus one flaky test
that calls the real language model (`test_mcp_call_manhua_direct_episode`, which sometimes gets an "Episode 1: ..." title); it passes alone.
