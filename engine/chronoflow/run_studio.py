import sys
import os
from pathlib import Path

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from aiohttp import web
from engine.chronoflow.server import init_app, PORT

def main():
    print("=" * 65)
    print("  [CHRONOFLOW STUDIO] Sliding Window Video Chaining Engine")
    print("=" * 65)
    print(f"  * UI Dashboard:    http://127.0.0.1:{PORT}")
    print(f"  * ComfyUI Backend: http://127.0.0.1:8188")
    print("  * Strategy:        Keyframe Chaining & Tail-Frame Extraction")
    print("=" * 65)
    
    app = init_app()
    web.run_app(app, host="127.0.0.1", port=PORT)

if __name__ == "__main__":
    main()
