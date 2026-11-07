# Troubleshooting (symptom -> check -> fix)

Cases are from this project. See `regeneration.md` for the loop.

| Symptom | Check | Fix |
|---|---|---|
| Camera pushes in / zooms | `evaluate` camera flag; is the camera sentence a push-in? | Static Shot sentence (Phase 1: 38% -> 0.8%) |
| Subject suddenly bigger in a "static" clip | subject lunging vs camera: border-ring zoom in report | Accept if it is the action; else shorten/soften the action |
| Scene jumps mid-clip (`p005`: close-up -> flying glider at 0.58 s) | cut flag with time; does the first frame show what the action needs? | `static_camera`, then `widen_frame` (a wider first frame fixed it); else one action per clip, split the shot |
| Hair/outfit/colour changes (`p004_1`, `p070`) | drift flag + contact sheet | simpler action, shorter clip, redraw frame, new seed |
| Screen goes dark or flashes (`p019_1`) | drift + flicker flags | remove light-event words, new seed |
| Glass/object changes state (juice appears) | contact sheet | remove result-implying verb; name the end state |
| Jets/planes instead of the vehicle | prompt wording | name what it is ("cloth-winged glider") + explicit "no jets, no airplanes" |
| Speech or music in a silent shot | ASR of the clip | `quiet` shot |
| Mouth drawn on a non-face speaker | picture | `FACELESS`: silent anchor, voice at master |
| Clip looks like a still | `motion` flag (< 0.3) | add the action; or accept a calm beat |
| Longer clip got worse | metrics 124 vs 56/73 frames | go back to short; split actions into shots |
| Same prompt gives the same bad clip | that is expected (deterministic) | change one input (seed or prompt clause) |
| Dialogue unclear / wrong words | ASR WER | check line length vs clip length; anchored voice; music level (-27 dB) |
| `ComfyUI workflow ... not ready` | `registry.preflight` shows missing nodes/models | start ComfyUI (`main.py --listen 127.0.0.1 --port 8188`) and run PanelFlow with `PANELFLOW_COMFYUI_WORKFLOW_DIR=E:\VIJAY SEKAR\ComfyUI\workflow`; do not download without approval |
| Generation stalls or OOM | ComfyUI queue, `nvidia-smi` (15 of 16 GB used is normal), Ollama loaded? | wait for the queue; `release_ollama`; one GPU job at a time |
| Engine edit has no effect | engine has no auto-reload | `launch_panelflow.ps1 -EngineOnly -ForceRestart` when no job is running |
| ChronoFlow shows "A+" for a bad clip | `chronoflow/reviewer.py` returns constants | ignore it; use `clip_eval` |
| Tracker says -160% pan / 354% zoom | inliers low, value over 50% | `suspected`; look at the frames |
