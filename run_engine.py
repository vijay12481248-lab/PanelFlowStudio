import os
import sys
from pathlib import Path

# Add panelflow directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

if sys.platform == "win32":
    import asyncio
    from asyncio.proactor_events import _ProactorBasePipeTransport
    orig_call_conn_lost = _ProactorBasePipeTransport._call_connection_lost
    def _safe_call_connection_lost(self, exc):
        try:
            orig_call_conn_lost(self, exc)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            pass
    _ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost

    try:
        # Ensure stdout and stderr handles exist when launched in background or no-window mode
        local_app_data = os.environ.get("LOCALAPPDATA")
        log_dir = Path(local_app_data) / "PanelFlow Studio" / "logs" if local_app_data else Path.home() / ".panelflow" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "engine.log"

        need_redirect = False
        if sys.stdout is None or not hasattr(sys.stdout, "write"):
            need_redirect = True
        else:
            try:
                sys.stdout.flush()
            except Exception:
                need_redirect = True

        if need_redirect:
            f = open(log_file, "a", encoding="utf-8", buffering=1)
            sys.stdout = f
            sys.stderr = f
    except Exception:
        pass

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, getattr(sys, "_MEIPASS"))

import uvicorn
from engine.config.settings import settings
from engine.api.app import app

if __name__ == "__main__":
    print(f"Starting {settings.app_name} Engine on http://{settings.api_host}:{settings.api_port}...")
    server = uvicorn.Server(uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
        access_log=False,
    ))
    restart_requested = False

    def request_restart():
        global restart_requested
        restart_requested = True
        server.should_exit = True

    app.state.request_restart = request_restart
    server.run()
    if restart_requested:
        # Re-execute only after Uvicorn releases the listener and runs shutdown.
        args = [sys.executable, *sys.argv[1:]] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
        os.execv(sys.executable, args)
