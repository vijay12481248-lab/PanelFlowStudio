"""Re-authorise YouTube (needed once after the scope change): prints the Google consent URL and waits until the owner approves it."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.youtube.auth import YouTubeAuth  # noqa: E402

a = YouTubeAuth()
print(a.begin(), flush=True)
while a._pending and not a._pending.get("done"):
    time.sleep(2)
print("error:", a._pending.get("error") or "none", flush=True)
