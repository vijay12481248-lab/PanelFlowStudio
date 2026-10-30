from engine.narration.artifacts import OcrDialogue, PanelFacts
from engine.narration.cache import ArtifactCache, cache_key


def _facts(pid="p1", text="hello"):
    return PanelFacts(
        panel_id=pid, order=1, is_story=True, shot="close", action="runs", emotion="fear",
        dialogue=[OcrDialogue(region_id="r1", text=text)], importance=3, confidence=0.9,
    )


def test_put_then_get_returns_equal_artifact(tmp_path):
    c = ArtifactCache(tmp_path)
    f = _facts()
    c.put("perceive", "k1", f)
    assert c.get("perceive", "k1", PanelFacts) == f


def test_prompt_change_misses_cache():
    a = cache_key("perceive", {"panel": "p1"}, "sha-A", "qwen3.5:9b", {"t": 0.1})
    b = cache_key("perceive", {"panel": "p1"}, "sha-B", "qwen3.5:9b", {"t": 0.1})
    assert a != b
    assert cache_key("perceive", {"panel": "p1"}, "sha-A", "qwen3.5:9b", {"t": 0.1}) == a


def test_key_ignores_dict_ordering():
    assert cache_key("s", {"a": 1, "b": 2}, "x", "m", {}) == cache_key("s", {"b": 2, "a": 1}, "x", "m", {})


def test_missing_key_returns_none(tmp_path):
    assert ArtifactCache(tmp_path).get("perceive", "nope", PanelFacts) is None


def test_unicode_round_trips(tmp_path):
    c = ArtifactCache(tmp_path)
    f = _facts(text="修炼者！ Él dijo: ¿qué?")
    path = c.put("perceive", "k1", f)
    assert "修炼者！ Él dijo: ¿qué?" in path.read_text(encoding="utf-8")
    assert c.get("perceive", "k1", PanelFacts) == f


def test_list_artifacts_round_trip(tmp_path):
    c = ArtifactCache(tmp_path)
    items = [_facts("p1"), _facts("p2")]
    c.put("perceive", "k1", items)
    assert c.get("perceive", "k1", PanelFacts) == items


def test_write_is_atomic_no_tmp_left(tmp_path):
    ArtifactCache(tmp_path).put("perceive", "k1", _facts())
    assert list(tmp_path.rglob("*.tmp")) == []
