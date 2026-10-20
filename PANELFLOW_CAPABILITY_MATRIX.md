# PanelFlow Studio Capability Matrix

Status meanings: **Verified** = exercised or directly inspected; **Partial** = code exists but the acceptance path is incomplete; **Gap** = not implemented or not verified.

| Capability | Status | Evidence / limitation |
|---|---|---|
| React/Tauri desktop shell | Verified | Desktop package builds; `cargo check` passes |
| FastAPI engine | Verified | `engine/api/app.py`, router architecture and port `8765` inspected |
| SQLite persistence | Partial | WAL/custom migrations exist; dependency environment prevents full runtime test |
| Durable jobs | Partial | Manager supports leases, cancellation, dependencies and retries; retry scheduling was repaired and needs full integration coverage |
| Project/workspace isolation | Partial | Existing services and workspace paths exist; security/path matrix needs dedicated review |
| Page/image acquisition | Verified | Acquisition tools, fixtures and acceptance tests present |
| Panel detection/order | Verified | Synthetic fixtures and unit tests present |
| OCR/text regions | Verified | OCR and text-region modules/tests present |
| Story analysis/provenance | Partial | Strong schemas/checkpoints/provenance; real-provider and fail-closed paths need full environment tests |
| Script adaptation | Partial | Existing adapter/editor/validator; end-to-end original-story acceptance not verified |
| TTS | Partial | Provider/service/synthesis code exists; stable voice and selective replacement need integration acceptance |
| Music generation | Gap/uncertain | Documentation references integrations, but no verified working provider path was found during this audit |
| Motion planning | Partial | Motion modules and acceptance scripts exist; artifact-level video review remains outstanding |
| FFmpeg/FFprobe | Verified installed | Executables found on PATH; actual export was not run in this audit |
| ComfyUI health | Verified | `127.0.0.1:8188`, version `0.42.0`, empty queue at audit time |
| ComfyUI node discovery | Verified | 2,695 node classes returned by `/object_info` |
| ComfyUI workflow discovery | Verified | 5 local workflow JSON files discovered |
| ComfyUI PanelFlow adapter | Partial | Client and read-only API bridge added; approved workflow registry and durable generation jobs remain |
| ComfyUI image generation | Gap | No PanelFlow-managed image submission/retrieval acceptance run yet |
| Character registry | Gap/partial | Data models and story concepts exist, but persistent canonical references and identity review are incomplete |
| Asset library/reuse | Partial | Workspace assets exist; approval/versioning and reuse decision engine are incomplete |
| Storyboard/shot planning | Partial | Story and motion structures exist; narrative-to-shot decision engine is incomplete |
| Hermes integration | Partial | Hermes supports MCP/delegation; PanelFlow-specific least-privilege MCP server is not implemented |
| Quality review loop | Partial | Validators and acceptance scripts exist; unified narrative/visual/audio/video QC state machine is missing |
| Provenance/rights | Partial | Rights-related models/docs exist; exportable rights clearance report and model-license registry are incomplete |
| Python reproducible setup | Gap | No complete visible lock/manifest; active environment misses test/runtime packages |
| Frontend automated tests | Gap/uncertain | Build passes; no complete installed TypeScript test runner was verified |
| Full regression suite | Blocked | `pytest` cannot start because the environment lacks it and backend dependencies |
| Commercial readiness | Gap | Licensing, cost approvals, backups, recovery and end-to-end acceptance remain incomplete |
