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

import uvicorn
from engine.config.settings import settings
from engine.api.app import app

if __name__ == "__main__":
    print(f"Starting {settings.app_name} Engine on http://{settings.api_host}:{settings.api_port}...")
    uvicorn.run(
        "engine.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )
