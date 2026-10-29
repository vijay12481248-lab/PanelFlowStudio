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

class TeeLogger:
    def __init__(self, original_stream, log_file):
        self.orig = original_stream
        self.file = log_file

    def write(self, data):
        if self.orig:
            try:
                self.orig.write(data)
                self.orig.flush()
            except Exception:
                pass
        if self.file:
            try:
                self.file.write(data)
                self.file.flush()
            except Exception:
                pass

    def flush(self):
        if self.orig:
            try: self.orig.flush()
            except Exception: pass
        if self.file:
            try: self.file.flush()
            except Exception: pass

    def isatty(self):
        return getattr(self.orig, "isatty", lambda: False)()

try:
    local_app_data = os.environ.get("LOCALAPPDATA")
    log_dir = Path(local_app_data) / "PanelFlow Studio" / "logs" if local_app_data else Path.home() / ".panelflow" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "engine.log"
    log_handle = open(log_file, "a", encoding="utf-8", buffering=1)
    sys.stdout = TeeLogger(sys.stdout, log_handle)
    sys.stderr = TeeLogger(sys.stderr, log_handle)
except Exception:
    pass

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, getattr(sys, "_MEIPASS"))

# Ensure PANELFLOW_ENGINE_TOKEN is loaded or generated so local API authentication succeeds
if not os.environ.get("PANELFLOW_ENGINE_TOKEN"):
    local_app_data = os.environ.get("LOCALAPPDATA")
    token_candidates = [
        Path(local_app_data) / "PanelFlow Studio" / "engine.token" if local_app_data else None,
        Path(__file__).parent / ".engine_token",
    ]
    loaded_token = ""
    for cand in token_candidates:
        if cand and cand.exists():
            try:
                content = cand.read_text(encoding="utf-8").strip()
                if content:
                    loaded_token = content
                    break
            except Exception:
                pass
    if not loaded_token:
        import secrets
        loaded_token = secrets.token_hex(32)
    os.environ["PANELFLOW_ENGINE_TOKEN"] = loaded_token
    for cand in token_candidates:
        if cand:
            try:
                cand.parent.mkdir(parents=True, exist_ok=True)
                cand.write_text(loaded_token, encoding="utf-8")
            except Exception:
                pass

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
    try:
        server.run()
    except Exception as exc:
        print(f"[FATAL] Engine server crashed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise

    if restart_requested:
        # Re-execute only after Uvicorn releases the listener and runs shutdown.
        args = [sys.executable, *sys.argv[1:]] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
        os.execv(sys.executable, args)
