"""SQLite store for the audience-intelligence system (own file `intel.db` in the app-data dir; never the app database).

Every metric row is a snapshot: (retrieved_at, source) are required, unknown values are NULL (never 0), and old snapshots are kept so
growth and decline can be analysed later. Phase 1 holds what research needs; later phases add tables as their entities appear.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS channel(id TEXT PRIMARY KEY, handle TEXT, title TEXT, country TEXT, created_at TEXT, category TEXT, style TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS channel_snapshot(channel_id TEXT NOT NULL REFERENCES channel(id), retrieved_at TEXT NOT NULL, source TEXT NOT NULL,
  subscribers INTEGER, views INTEGER, videos INTEGER, PRIMARY KEY(channel_id, retrieved_at, source));
CREATE TABLE IF NOT EXISTS video(id TEXT PRIMARY KEY, channel_id TEXT REFERENCES channel(id), title TEXT, published_at TEXT, duration_s REAL, is_short INTEGER,
  category TEXT, style TEXT, concept TEXT, hook TEXT, structure TEXT, payoff TEXT, ending TEXT, analysis_basis TEXT);
CREATE TABLE IF NOT EXISTS video_snapshot(video_id TEXT NOT NULL REFERENCES video(id), retrieved_at TEXT NOT NULL, source TEXT NOT NULL,
  views INTEGER, likes INTEGER, comments INTEGER, PRIMARY KEY(video_id, retrieved_at, source));
CREATE TABLE IF NOT EXISTS audience_signal(id INTEGER PRIMARY KEY, retrieved_at TEXT NOT NULL, source TEXT NOT NULL, niche TEXT, kind TEXT, text TEXT NOT NULL,
  video_id TEXT, evidence TEXT);
CREATE TABLE IF NOT EXISTS creative_pattern(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, why_it_works TEXT, evidence_video_ids TEXT, status TEXT NOT NULL DEFAULT 'hypothesis');
CREATE TABLE IF NOT EXISTS credit_ledger(id INTEGER PRIMARY KEY, at TEXT NOT NULL, tool TEXT NOT NULL, credits INTEGER NOT NULL, note TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_path() -> Path:
    from engine.config.settings import Settings
    return Settings().app_data_dir / "intel.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def upsert_channel(db, id: str, *, source: str, retrieved_at: str | None = None, subscribers=None, views=None, videos=None, **fields) -> None:
    cols = ("handle", "title", "country", "created_at", "category", "style", "notes")
    given = {k: v for k, v in fields.items() if k in cols and v is not None}
    db.execute("INSERT OR IGNORE INTO channel(id) VALUES(?)", (id,))
    for k, v in given.items():
        db.execute(f"UPDATE channel SET {k}=? WHERE id=?", (v, id))
    db.execute("INSERT OR REPLACE INTO channel_snapshot VALUES(?,?,?,?,?,?)", (id, retrieved_at or now(), source, subscribers, views, videos))
    db.commit()


def upsert_video(db, id: str, channel_id: str | None, *, source: str, retrieved_at: str | None = None, views=None, likes=None, comments=None, **fields) -> None:
    cols = ("title", "published_at", "duration_s", "is_short", "category", "style", "concept", "hook", "structure", "payoff", "ending", "analysis_basis")
    given = {k: v for k, v in fields.items() if k in cols and v is not None}
    db.execute("INSERT OR IGNORE INTO video(id, channel_id) VALUES(?,?)", (id, channel_id))
    for k, v in given.items():
        db.execute(f"UPDATE video SET {k}=? WHERE id=?", (v, id))
    db.execute("INSERT OR REPLACE INTO video_snapshot VALUES(?,?,?,?,?,?)", (id, retrieved_at or now(), source, views, likes, comments))
    db.commit()


def log_credits(db, tool: str, credits: int, note: str = "") -> None:
    db.execute("INSERT INTO credit_ledger(at, tool, credits, note) VALUES(?,?,?,?)", (now(), tool, credits, note))
    db.commit()


def add_signal(db, kind: str, text: str, *, source: str, niche: str | None = None, video_id: str | None = None, evidence: dict | None = None) -> None:
    db.execute("INSERT INTO audience_signal(retrieved_at, source, niche, kind, text, video_id, evidence) VALUES(?,?,?,?,?,?,?)",
               (now(), source, niche, kind, text, video_id, json.dumps(evidence) if evidence else None))
    db.commit()


def latest_video_views(db, channel_id: str) -> list[int | None]:
    """Most recent snapshot's views for every video of a channel (unknown stays None)."""
    rows = db.execute("""SELECT s.views FROM video v JOIN video_snapshot s ON s.video_id=v.id
        WHERE v.channel_id=? AND s.retrieved_at=(SELECT MAX(retrieved_at) FROM video_snapshot WHERE video_id=v.id)""", (channel_id,)).fetchall()
    return [r["views"] for r in rows]
