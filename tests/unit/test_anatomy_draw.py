from types import SimpleNamespace

from engine.original.anatomy import draw
from engine.original.anatomy.review import AnatomyReport
from engine.original.anatomy.rules import Defect


class Art:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, negative, w, h, seed, prefix, **kw):
        self.calls.append((prompt, negative, seed, kw))
        return SimpleNamespace(png=b"plain-png")


def test_without_the_check_it_is_the_plain_art_engine_call():
    art = Art()
    png, report = draw.draw_picture(art, prompt="a girl", negative_prompt="blurry", width=768, height=1344, seed=5, prefix="p", reference_image="ref.png")
    assert png == b"plain-png" and report is None
    assert art.calls == [("a girl", "blurry", 5, {"workflow_id": "hidream_i1_fast", "reference_image": "ref.png"})]


def test_with_the_check_it_runs_the_redraw_loop_and_returns_a_json_report(monkeypatch):
    seen = {}

    def fake_checked(art_engine, judges, **kw):
        seen.update(kw, judges=judges)
        rep = AnatomyReport(status="defects", confirmed=[Defect(kind="extra_hands", judge="a", tile="whole", detail="x")], suspected=[], judges=["a", "b"])
        return SimpleNamespace(png=b"checked-png", report=rep, status="best_effort", seed=99, prompt="a girl Remember: x", attempts=[{"attempt": 0}, {"attempt": 1}])

    monkeypatch.setattr(draw, "generate_checked", fake_checked)
    png, report = draw.draw_picture(Art(), prompt="a girl", width=768, height=1344, seed=5, prefix="p", reference_image="ref.png", check=True, judges=["j"])
    assert png == b"checked-png" and seen["reference_images"] == ["ref.png"] and seen["judges"] == ["j"]
    assert report == {"status": "best_effort", "seed": 99, "attempts": 2, "confirmed": ["extra_hands"], "suspected": [], "prompt": "a girl Remember: x"}
