"""Load saved vidIQ channel_search / similar_channels result files into the intel store and print a compact digest.

    .venv\\Scripts\\python.exe -I tools/intel/ingest_channels.py FILE [FILE ...]   (each file = one 5-credit vidIQ call, logged to the ledger)
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.intel import metrics, store  # noqa: E402

OUT = ROOT / "output" / "intel"


def main(files):
    sys.stdout.reconfigure(encoding="utf-8")
    db = store.connect()
    seen = {}
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        store.log_credits(db, "channel_search|similar_channels", 5, Path(f).name)
        t = store.now()
        for c in d["channels"]:
            seen[c["channelId"]] = c
            store.upsert_channel(db, c["channelId"], source="vidiq:channel_search", retrieved_at=t, subscribers=c.get("subscriberCount"),
                                 views=c.get("viewCount"), videos=c.get("videoCount"), handle=c.get("handle"), title=c.get("channelTitle"),
                                 country=c.get("country"), created_at=c.get("publishedAt"), category=c.get("niche"),
                                 style=", ".join(c.get("subNiches") or []) or None)
    rows = sorted(seen.values(), key=lambda c: -(c.get("avgViews") or 0))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "channels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["channelId", "title", "handle", "subs", "views", "videos", "avgViews", "viewsPerSub", "type", "country", "niche", "subNiches", "views30d%", "shorts30d"])
        for c in rows:
            w.writerow([c["channelId"], c["channelTitle"], c["handle"], c["subscriberCount"], c["viewCount"], c["videoCount"], round(c["avgViews"] or 0),
                        metrics.views_to_subs(c["viewCount"], c["subscriberCount"]), c.get("channelType"), c.get("country"), c.get("niche"),
                        "|".join(c.get("subNiches") or []), c.get("viewsGrowth30d"), c.get("shortVideoCount30d")])
    print(f"{len(seen)} unique channels from {len(files)} files -> {OUT / 'channels.csv'}")
    for c in rows[:60]:
        print(f"{c['channelTitle'][:26]:26} {str(c['handle'])[:24]:24} subs={c['subscriberCount'] or 0:>9,} avg={round(c['avgViews'] or 0):>9,} "
              f"n={c['videoCount']:>5} {c.get('channelType') or '-':5} {c.get('country') or '-':2} {'|'.join(c.get('subNiches') or [])[:40]}")


if __name__ == "__main__":
    main(sys.argv[1:])
