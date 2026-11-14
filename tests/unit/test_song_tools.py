"""tools/songs: the catalog must be well formed before it costs GPU hours, and the lyric-error maths must be right."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "songs"))
import make_songs as ms  # noqa: E402

REQUIRED = {"id", "title", "theme", "lang", "bpm", "key", "dur", "caption", "lyrics"}


def test_catalog_is_complete_and_well_formed():
    songs = ms.catalog()
    assert len(songs) >= 100 and [s for s in songs if s['id'] == '100']
    for s in songs:
        assert REQUIRED <= s.keys(), s["id"]
        assert s["lang"] in ("en", "ja", "te"), s["id"]
        assert 60 <= s["bpm"] <= 180 and 150 <= s["dur"] <= 240, s["id"]
        assert "[Chorus" in s["lyrics"] and "[Verse" in s["lyrics"], s["id"]
        assert not any(name in s["caption"].lower() for name in ("taylor", "beatles", "ed sheeran", "yoasobi")), "no artist sound-alikes"


def test_wer_and_word_extraction():
    assert ms.wer(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert ms.wer(["a", "b", "c", "d"], ["a", "x", "c"]) == 0.5  # one substitution + one deletion
    assert ms.words("[Chorus]\nKeep warm (oh)\nDon't skip", "en") == ["keep", "warm", "don't", "skip"]
    assert ms.words("[Verse 1]\n朝の 玄関、", "ja") == list("朝の玄関")
