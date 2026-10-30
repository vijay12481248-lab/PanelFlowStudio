"""
ACE-Step 1.5 Background Daemon Manager for PanelFlow Studio.

Starts or checks the ACE-Step 1.5 REST API daemon on port 8001.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.audio.providers.ace_step import local_music_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Start or probe ACE-Step 1.5 API daemon.")
    parser.add_argument("--check-only", action="store_true", help="Only check health without auto-starting.")
    args = parser.parse_args()

    print("==================================================")
    print(" PanelFlow Studio: ACE-Step 1.5 Service Manager   ")
    print("==================================================")

    health = local_music_provider.check_health()
    if health["available"]:
        print(f"[STATUS] ACE-Step is already RUNNING at {health['base_url']}")
        print(f"         Service: {health.get('service')}")
        print(f"         Model:   {health.get('loaded_model')}")
        return 0

    if args.check_only:
        print("[STATUS] ACE-Step daemon is OFFLINE.")
        return 1

    print("[ACTION] ACE-Step daemon is offline. Starting background service...")
    started = local_music_provider.ensure_service_running()
    if started:
        h = local_music_provider.check_health()
        print(f"[SUCCESS] ACE-Step 1.5 daemon launched and READY at {h['base_url']}")
        print(f"          Model Checkpoint: {h.get('loaded_model')}")
        return 0
    else:
        print("[ERROR] Failed to start ACE-Step daemon. Please check C:\\Tools\\ACE-Step-1.5")
        return 1


if __name__ == "__main__":
    sys.exit(main())
