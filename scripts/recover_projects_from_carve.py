"""Recover projects (and everything hanging off them) from freed pages of an emptied panelflow.db.

    python scripts/recover_projects_from_carve.py <emptied-db-copy> <live-db> [--apply]

Without --apply it only reports. With --apply it INSERTs rows for projects that are not in the live DB yet (never updates or
deletes anything). The source file is only read.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sqlite_carve import carve  # noqa: E402

UUID_LEN = 36
_DT = re.compile(r"^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d")


def _fits(col_type: str, notnull: bool, v) -> bool:
    """Does a carved value fit the column's declared type? Used to tell apart tables with the same column count."""
    if v is None:
        return not notnull
    t = col_type.upper()
    m = re.search(r"\((\d+)\)", t)
    if t.startswith(("VARCHAR", "TEXT", "JSON")):
        return isinstance(v, str) and (not m or len(v) <= int(m.group(1)))
    if t.startswith("DATETIME"):
        return isinstance(v, str) and bool(_DT.match(v))
    if t.startswith("BOOLEAN"):
        return v in (0, 1)
    if t.startswith(("INTEGER", "BIGINT")):
        return isinstance(v, int)
    if t.startswith(("FLOAT", "REAL")):
        return isinstance(v, (int, float))
    return True


def _matches(info, v) -> bool:
    return len(v) == len(info) and all(_fits(ty, nn, x) for (_, ty, nn), x in zip(info, v))


def main(src: str, live_path: str, apply: bool) -> None:
    live = sqlite3.connect(f"file:{live_path}?mode=ro", uri=True)
    schema, info = {}, {}
    for (t,) in live.execute("select name from sqlite_master where type='table'"):
        info[t] = [(r[1], r[2], bool(r[3])) for r in live.execute(f'pragma table_info("{t}")')]
        cols = [r[1] for r in live.execute(f'pragma table_info("{t}")')]
        fks = {r[3]: r[2] for r in live.execute(f'pragma foreign_key_list("{t}")')}
        schema[t] = (cols, fks)
    have = {r[0] for r in live.execute("select id from projects")}

    by_table = defaultdict(list)
    ambiguous = 0
    for page, rowid, vals in carve(src):
        fit = [t for t in info if _matches(info[t], vals)]
        if len(fit) == 1:
            by_table[fit[0]].append(vals)
        elif len(fit) > 1:
            ambiguous += 1                # fits several tables (e.g. same shape): never guess
    print(f"records that fit more than one table and were dropped: {ambiguous}")

    cols, _ = schema["projects"]
    pk_i, upd_i = 0, cols.index("updated_at")
    projects = {}
    for v in by_table["projects"]:
        if len(v[0]) == UUID_LEN and v[2].isupper():
            if v[0] not in projects or str(v[upd_i]) >= str(projects[v[0]][upd_i]):
                projects[v[0]] = v
    new_ids = {pid for pid in projects if pid not in have}
    print(f"projects found: {len(projects)}  already in live DB: {len(projects) - len(new_ids)}  recoverable new: {len(new_ids)}")

    out = {"projects": [projects[p] for p in new_ids]}
    owned = {"projects": set(new_ids)}          # table -> primary keys we accepted
    changed = True
    done = {"projects"}
    # closure over foreign keys: a table is resolved once every parent it points to is resolved
    while changed:
        changed = False
        for t, (tcols, fks) in schema.items():
            if t in done or t == "ocr_cache" or not set(fks.values()) <= done:
                continue
            fk_idx = [(tcols.index(c), parent) for c, parent in fks.items()]
            if not fk_idx:
                continue
            best = {}
            for v in by_table[t]:
                ok = all(isinstance(v[i], str) and v[i] in owned[parent] for i, parent in fk_idx)
                if not ok:
                    continue
                key = v[0]
                if key not in best or ("updated_at" in tcols and str(v[tcols.index("updated_at")]) >= str(best[key][tcols.index("updated_at")])):
                    best[key] = v
            out[t] = list(best.values())
            owned[t] = set(best)
            done.add(t)
            changed = True

    for t in schema:
        if t in out and t != "projects" or t == "projects":
            print(f"  {t:26s} {len(out.get(t, [])):6d}")
    for v in sorted(out["projects"], key=lambda r: r[1]):
        pages = sum(1 for p in out.get("pages", []) if p[schema['pages'][0].index('project_id')] == v[0])
        panels = sum(1 for p in out.get("panels", []) if p[schema['panels'][0].index('project_id')] == v[0])
        print(f"  - {v[1][:60]:60s} stage={v[8]:15s} pages={pages:3d} panels={panels:4d} workspace_exists={os.path.isdir(v[7])}")

    if not apply:
        print("dry run: nothing written")
        return
    con = sqlite3.connect(live_path, timeout=30)
    con.execute("pragma foreign_keys=off")
    with con:
        for t in ("projects", *[t for t in schema if t not in ("projects",) and t in out]):
            rows = out[t]
            if not rows:
                continue
            q = ",".join("?" * len(schema[t][0]))
            pk = schema[t][0][0]
            for r in rows:
                con.execute(f'insert or ignore into "{t}" values ({q})', r)
    for t, rows in out.items():
        got = con.execute(f'select count(*) from "{t}" where "{schema[t][0][0]}" in ({",".join("?" * len(rows))})', [r[0] for r in rows]).fetchone()[0] if rows else 0
        print(f"verify {t:26s} wanted={len(rows):5d} in db={got:5d}")
    con.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--apply" in sys.argv)
