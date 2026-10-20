# Restarting the PanelFlow engine

Run `launch_panelflow.bat` or `launch_panelflow.ps1` to restart an existing backend and launch the desktop application. The launcher lists active jobs and renders, including job IDs, status, progress, project, and start time. It asks whether to cancel them before restarting. Answering no keeps the engine and jobs running and continues to launch the UI. In a source checkout it prefers `run_engine.py` so code changes take effect.

For a backend-only restart, from the repository root:

```powershell
.\launch_panelflow.ps1 -EngineOnly
```

To explicitly cancel the listed active jobs and renders and restart without the cancellation prompt:

```powershell
.\launch_panelflow.bat -CancelJobs
# Backend only:
.\launch_panelflow.ps1 -EngineOnly -CancelJobs
```

The launcher waits up to 30 seconds for jobs to leave their active states; it keeps the engine running if cancellation remains pending. Cancellation stops unfinished work; completed story panel checkpoints are retained by the story pipeline.

The floating **Jobs** panel in the UI shows active and recent background jobs and offers **Cancel job**. Story analysis also has **Cancel analysis** below its progress details. Alerts announce submission, startup, retry, completion, cancellation, and failure. **View Job Details** opens a status card refreshed every five seconds with progress, submission/start times, engine connection health, and worker lease heartbeat. A current worker heartbeat confirms the worker lease is renewed; it does not prove the model is generating tokens.

The **Restart Engine** button appears beside the engine connection indicator on the dashboard and project screens. It requests a graceful shutdown, re-executes the engine after its listener closes, and waits for a different healthy engine instance. Finish or cancel active jobs and renders first.

The UI restart endpoint requires a loopback client and the `X-PanelFlow-Control: restart` header. Engines launched directly through `uvicorn` cannot restart themselves; launch through `run_engine.py` instead.

Existing running processes must be restarted once with the updated launcher before they support the button. Existing packaged desktop executables must be rebuilt to include the new UI; building the web assets alone does not modify an already compiled desktop executable.

The launcher selects the newest desktop executable by modification time across portable, release, and debug builds, including dated `panelflow-desktop-*.exe` files. An updated native executable can sit beside a running, locked older executable. Close old desktop windows before relaunching to avoid confusing the old UI with the new one.

Verification:

```powershell
python -m pytest tests/unit/test_engine_restart.py tests/unit/test_visual_storytelling.py -q
powershell -NoProfile -File tests/unit/test_launcher_restart.ps1
npm --workspace=@panelflow/desktop run build
```

Restart tests mock process control; they do not stop the developer's running engine.
