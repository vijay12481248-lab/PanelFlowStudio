"""Connect YouTube and upload ONE finished episode as a PRIVATE video (a safe end-to-end test).

Run it in your own terminal so the OAuth client secret is typed there and never pasted anywhere else:

    .venv\\Scripts\\python.exe scripts\\youtube_test_upload.py --series-root <series folder> --series moon_tales --episode 1 --made-for-kids yes

Add --dry-run to check what would be uploaded without contacting Google at all.
"""
from __future__ import annotations

import argparse
import getpass
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.original import upload as up  # noqa: E402
from engine.original.series import SeriesStore  # noqa: E402
from engine.youtube.auth import AuthError, YouTubeAuth  # noqa: E402
from engine.youtube.client import YouTubeClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series-root", required=True, help="folder that contains <series>/series.json")
    ap.add_argument("--series", required=True)
    ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--made-for-kids", choices=["yes", "no"], required=True,
                    help="your legal declaration for this video: is it made for kids (COPPA)?")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    store = SeriesStore(Path(a.series_root))
    kids = a.made_for_kids == "yes"
    meta, video, thumb = up.plan_upload(store, a.series, a.episode, made_for_kids=kids)  # private, no schedule
    print(f"Video     : {video} ({video.stat().st_size / 1e6:.1f} MB)")
    print(f"Title     : {meta.title}")
    print(f"Privacy   : {meta.privacy} (this test never makes anything public)")
    print(f"Kids      : {kids}   Synthetic-media flag: {meta.synthetic}")
    print(f"Tags      : {meta.tags[:8]}")
    print(f"Thumbnail : {thumb}")
    if a.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    auth = YouTubeAuth()
    if not auth.status()["connected"]:
        if not auth.status()["configured"]:
            print("\nPaste the OAuth client from Google Cloud (Credentials -> OAuth client ID -> Desktop app).")
            auth.store.set_client(input("Client ID: ").strip(), getpass.getpass("Client secret (hidden): ").strip())
        url = auth.begin()
        print("\nOpening your browser to approve access. If it does not open, copy this link into it:\n" + url)
        webbrowser.open(url)
        for _ in range(300):
            st = auth.status()
            if st["connected"]:
                break
            if st["error"]:
                print("Authorisation failed:", st["error"])
                return 1
            time.sleep(1)
        else:
            print("Timed out waiting for approval.")
            return 1
        print("Connected.")

    if input("\nUpload this video as PRIVATE now? [y/N] ").strip().lower() != "y":
        print("Stopped; nothing uploaded.")
        return 0
    last = [-1]

    def progress(p: float) -> None:
        if int(p * 10) != last[0]:
            last[0] = int(p * 10)
            print(f"  {int(p * 100)}%")

    yt = YouTubeClient(auth)
    try:
        res = up.upload_episode(store, a.series, a.episode, yt, made_for_kids=kids)
    except (AuthError, Exception) as e:  # noqa: BLE001
        print("Upload failed:", e)
        return 1
    print("Done:", res["url"], "(private - open YouTube Studio to review it)")
    if res.get("warning"):
        print("Note:", res["warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
