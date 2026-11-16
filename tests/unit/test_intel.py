from engine.intel import metrics, store


def test_ratio_and_unknowns():
    assert metrics.views_to_subs(5_000_000, 50_000) == 100
    assert metrics.views_to_subs(10_000_000, 100_000_000) == 0.1
    assert metrics.views_to_subs(None, 10) is None
    assert metrics.views_to_subs(10, None) is None
    assert metrics.views_to_subs(10, 0) is None  # hidden subscriber count is unknown, not zero


def test_summarize_skips_unknown_and_counts_thresholds():
    s = metrics.summarize([2_000_000, 600_000, 150_000, 10_000, None])
    assert s["n"] == 4 and s["median"] == 375_000
    assert s["share_over"][100_000] == 0.75 and s["share_over"][1_000_000] == 0.25 and s["share_over"][10_000_000] == 0
    assert metrics.summarize([None])["median"] is None


def test_outlier_score():
    assert metrics.outlier_score(1000, [100, 100, 100]) == 10
    assert metrics.outlier_score(1000, []) is None
    assert metrics.outlier_score(None, [100]) is None


def test_store_keeps_history_and_null(tmp_path):
    db = store.connect(tmp_path / "i.db")
    store.upsert_channel(db, "UC1", source="t", retrieved_at="2026-11-01", subscribers=100, title="A")
    store.upsert_channel(db, "UC1", source="t", retrieved_at="2026-11-16", subscribers=None)  # hidden count later: keep both snapshots
    assert db.execute("SELECT COUNT(*) FROM channel_snapshot").fetchone()[0] == 2
    assert db.execute("SELECT title FROM channel WHERE id='UC1'").fetchone()[0] == "A"
    store.upsert_video(db, "v1", "UC1", source="t", retrieved_at="2026-11-01", views=10)
    store.upsert_video(db, "v1", "UC1", source="t", retrieved_at="2026-11-16", views=50, likes=None)
    store.upsert_video(db, "v2", "UC1", source="t", retrieved_at="2026-11-16")
    assert sorted(store.latest_video_views(db, "UC1"), key=lambda x: (x is None, x)) == [50, None]
    store.log_credits(db, "outliers", 5)
    assert db.execute("SELECT SUM(credits) FROM credit_ledger").fetchone()[0] == 5
