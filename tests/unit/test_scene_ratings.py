"""Task 1 of the scene-director plan: owner ratings of delivered pictures and the numbers computed from them."""
from engine.original.scene_ratings import Rating, load_ratings, save_rating, summary


def _r(brief_id: str, good: bool, reason: str = "", mode: str = "raw", seconds: float = 10.0) -> Rating:
    return Rating(brief_id=brief_id, mode=mode, good=good, reason=reason, seconds=seconds)


def test_summary_counts_good_rate_and_reasons():
    s = summary([_r("a", True), _r("b", True), _r("c", False, "pose")])
    assert s["n"] == 3
    assert s["good_rate"] == 2 / 3
    assert s["by_reason"] == {"pose": 1}


def test_summary_empty_is_zero():
    s = summary([])
    assert s == {"n": 0, "good_rate": 0.0, "by_reason": {}, "mean_seconds": 0.0}


def test_summary_mean_seconds():
    assert summary([_r("a", True, seconds=10), _r("b", False, "style", seconds=20)])["mean_seconds"] == 15.0


def test_save_rating_replaces_same_brief_and_mode(tmp_path):
    p = tmp_path / "ratings.json"
    save_rating(p, _r("a", False, "pose"))
    save_rating(p, _r("a", True))
    rows = load_ratings(p)
    assert len(rows) == 1
    assert rows[0].good is True


def test_same_brief_in_two_modes_is_two_ratings(tmp_path):
    p = tmp_path / "ratings.json"
    save_rating(p, _r("a", False, "pose", mode="raw"))
    save_rating(p, _r("a", True, mode="director"))
    assert {(r.mode, r.good) for r in load_ratings(p)} == {("raw", False), ("director", True)}


def test_load_missing_file_is_empty(tmp_path):
    assert load_ratings(tmp_path / "nope.json") == []
