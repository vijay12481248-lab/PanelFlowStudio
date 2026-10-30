"""report.json and report.html for an EvalReport."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

from engine.narration.eval.metrics import TARGETS, ChapterMetrics, EvalReport

_COLS = ("gate", "grounded", "pipeline_pass", "coverage", "hallucinated_names", "fallback_share", "preference")
_NOTE = ("grounded is judged by the eval judge on every final line, fallbacks included. pipeline_pass is the "
         "pipeline's own grounded pass rate. coverage equals 1 - fallback_share, so it is not an independent measure.")


def _bad(name: str, value) -> bool:
    if value is None:
        return False
    if name == "gate":
        return value == "failed"
    return value != 0 if name == "hallucinated_names" else name in TARGETS and value < TARGETS[name]


def _row(m: ChapterMetrics) -> str:
    cells = "".join(
        f'<td class="{"bad" if _bad(c, getattr(m, c)) else "ok"}">'
        f'{"-" if getattr(m, c) in (None, "") else html.escape(f"{getattr(m, c):.2f}" if isinstance(getattr(m, c), float) else str(getattr(m, c)))}</td>'
        for c in _COLS)
    return f"<tr><td>{html.escape(m.slug)}</td>{cells}</tr>"


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spot = "".join(
        f"<tr><td>{html.escape(s['slug'])}</td><td>{html.escape(s['text'])}</td><td>{html.escape(s.get('facts', ''))}</td>"
        f"<td>{'yes' if s['grounded'] else 'no'}</td><td>{html.escape(s['reason'])}</td></tr>" for s in report.spotcheck)
    page = (
        "<!doctype html><meta charset=utf-8><title>Narration eval</title>"
        "<style>td,th{border:1px solid #888;padding:2px 8px}.bad{background:#f99}.ok{background:#cfc}</style>"
        f"<h1>Narration eval {html.escape(report.created)}</h1><p>{html.escape(_NOTE)}</p><table><tr><th>chapter</th>"
        + "".join(f"<th>{c}</th>" for c in _COLS) + "</tr>"
        + "".join(_row(m) for m in [*report.chapters, report.totals])
        + "</table><h2>Spot check</h2><table><tr><th>chapter</th><th>line</th><th>panel facts</th><th>grounded</th><th>reason</th></tr>"
        + spot + "</table>")
    jp, hp = out / "report.json", out / "report.html"
    for path, text in ((jp, json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=1)), (hp, page)):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return jp, hp
