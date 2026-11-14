"""Baseline for the Scene Director (docs/SCENE_DIRECTOR.md): run the 24 vague briefs, time each picture, write a contact sheet the owner rates.

    .venv\\Scripts\\python.exe tools/scene_director/baseline.py --mode raw --out <dir>

mode raw: the brief goes straight to ArtEngine (what a lazy user gets today). Mode director is added with the scene run loop (plan Task 6).
ComfyUI must be running (see AGENTS.md).
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BRIEFS = Path(__file__).with_name("baseline_briefs.json")
SIZE = (1344, 768)


def seed_for(brief_id: str) -> int:
    return 1000 + sum(ord(c) * (i + 1) for i, c in enumerate(brief_id))  # stable across runs and modes


def run(briefs: list[dict], mode: str, out: Path, art_engine) -> list[dict]:
    """One picture per brief. A failing brief is recorded with `error` and the batch carries on."""
    out.mkdir(parents=True, exist_ok=True)
    if mode != "raw":
        raise ValueError(f"unknown mode {mode!r}")
    results: list[dict] = []
    for b in briefs:
        row = {"id": b["id"], "scene_type": b["scene_type"], "text": b["text"], "mode": mode, "file": "", "seconds": 0.0, "error": ""}
        t0 = time.time()
        try:
            img = art_engine.generate(b["text"], "", SIZE[0], SIZE[1], seed_for(b["id"]), prefix=f"scene_baseline_{mode}")
            name = f"{b['id']}.png"
            (out / name).write_bytes(img.png)
            row["file"] = name
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden; the batch must finish
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        row["seconds"] = round(time.time() - t0, 1)
        results.append(row)
        (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"{b['id']}: {row['seconds']}s {row['error'] or 'ok'}", flush=True)
    write_contact_sheet(results, out, mode)
    return results


def write_contact_sheet(results: list[dict], out: Path, mode: str) -> Path:
    cards = []
    for r in results:
        if not r["file"]:
            cards.append(f'<div class="card"><p><b>{html.escape(r["id"])}</b> failed: {html.escape(r["error"])}</p></div>')
            continue
        cards.append(
            f'<div class="card" data-id="{html.escape(r["id"])}" data-seconds="{r["seconds"]}">'
            f'<img src="{html.escape(r["file"])}" loading="lazy"><p><b>{html.escape(r["id"])}</b> - {html.escape(r["text"])} ({r["seconds"]} s)</p>'
            '<button onclick="rate(this,true)">Good</button> <button onclick="rate(this,false)">Not good</button> '
            '<select><option value="">reason (if not good)</option><option>emotion</option><option>pose</option><option>camera</option>'
            '<option>identity</option><option>style</option><option>other</option></select></div>'
        )
    page = f"""<!doctype html><meta charset="utf-8"><title>Scene Director baseline ({mode})</title>
<style>body{{font:15px system-ui;margin:16px;background:#111;color:#eee}}.card{{margin:0 0 24px;max-width:960px}}img{{width:100%}}
button{{padding:6px 14px}}.card.good{{outline:3px solid #3a3}}.card.bad{{outline:3px solid #c44}}</style>
<h2>Rate each picture: does it match what you would imagine from the sentence?</h2><button onclick="dl()">Download ratings.json</button>
{''.join(cards)}
<script>
const ratings={{}};
function rate(btn,good){{const c=btn.closest('.card');const reason=c.querySelector('select').value;
ratings[c.dataset.id]={{brief_id:c.dataset.id,mode:'{mode}',good:good,reason:good?'':(reason||'other'),seconds:parseFloat(c.dataset.seconds)}};
c.className='card '+(good?'good':'bad');}}
function dl(){{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(Object.values(ratings),null,2)],{{type:'application/json'}}));
a.download='ratings.json';a.click();}}
</script>"""
    p = out / "contact_sheet.html"
    p.write_text(page, encoding="utf-8")
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="raw")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    from engine.comfyui.art import ArtEngine

    briefs = json.loads(BRIEFS.read_text(encoding="utf-8"))
    if a.limit:
        briefs = briefs[: a.limit]
    run(briefs, a.mode, Path(a.out), ArtEngine())


if __name__ == "__main__":
    main()
