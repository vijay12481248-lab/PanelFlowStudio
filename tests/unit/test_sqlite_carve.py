"""The carver must get deleted rows back out of the file, including records that spill onto overflow pages."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from sqlite_carve import carve  # noqa: E402
from recover_projects_from_carve import _matches  # noqa: E402


def test_rows_deleted_from_a_table_are_carved_back_including_overflow_text(tmp_path):
    db = tmp_path / "x.db"
    c = sqlite3.connect(db)
    c.execute("create table t (id integer primary key, name text, n integer, score real, blob_col blob, spare text)")
    big = "settings-" + "x" * 20000                      # far beyond one 4 KB page: stored on overflow pages
    rows = [(i, f"row {i} é", i * 7, i / 4, bytes([i % 256]) * 5, None) for i in range(1, 3001)] + [(5000, big, -5, 2.5, b"", None)]
    c.executemany("insert into t values (?,?,?,?,?,?)", rows)
    c.commit()
    c.execute("delete from t")                             # emptied, like the user's database
    c.commit()
    c.close()
    got = {r: v for _, r, v in carve(db)}
    # a table that fits in its single root page is wiped when emptied; one spanning many leaf pages keeps them in the freed pages
    assert sum(1 for r in got if r != 5000) >= 2700
    assert got[1500][1:] == ["row 1500 é", 10500, 375.0, bytes([1500 % 256]) * 5, None]
    assert got[5000][1] == big                             # overflow chain reassembled
    assert got[5000][2] == -5


def test_type_fit_tells_apart_tables_with_the_same_column_count():
    pages = [("id", "VARCHAR(36)", True), ("project_id", "VARCHAR(36)", True), ("page_number", "INTEGER", True), ("created_at", "DATETIME", True)]
    assets = [("id", "VARCHAR(36)", True), ("project_id", "VARCHAR(36)", True), ("filename", "VARCHAR(255)", True), ("created_at", "DATETIME", True)]
    row = ["a" * 36, "b" * 36, 4, "2026-11-02 18:08:43.123"]
    assert _matches(pages, row) and not _matches(assets, row)       # an int is not a filename
    assert not _matches(pages, ["a" * 36, "b" * 36, 4, "not a date"])
    assert not _matches(pages, ["a" * 37, "b" * 36, 4, "2026-11-02 18:08:43"])   # too long for VARCHAR(36)
    assert not _matches(pages, ["a" * 36, None, 4, "2026-11-02 18:08:43"])       # NULL in NOT NULL
