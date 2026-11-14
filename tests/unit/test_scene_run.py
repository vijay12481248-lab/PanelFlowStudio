"""Task 6 of the scene-director plan: the fast-path run loop (fake art engine, scripted checks, no GPU)."""
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from engine.original import scene_run as sr
from engine.original.models import ItemVerdict, Review
from engine.original.scene_run import SceneBudget, generate_scene
from scene_fixtures import fight_plan

STRIKE = "an adult man with short black hair, scarred cheek, worn blue coat is striking"


def png(color="grey") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(buf, "PNG")
    return buf.getvalue()


class FakeEngine:
    def __init__(self):
        self.calls: list[dict] = []

    def generate(self, prompt, negative, width, height, seed, prefix="x", *, timeout=0, is_cancelled=lambda: False, **kw):
        self.calls.append({"prompt": prompt, "negative": negative, "seed": seed, "size": (width, height)})
        return SimpleNamespace(png=png(("red", "green", "blue", "white")[len(self.calls) % 4]), width=width, height=height, workflow_id="qwen_image_21",
                               workflow_sha256="x", prompt_id=f"p{len(self.calls)}")


def review(decision, score, failed=(), confidence=0.9, reasons=()):
    items = [ItemVerdict(item=t, critical=True, verdict="missing", confidence=0.9, vision="no", description_says=False, kind="pose") for t in failed]
    items.append(ItemVerdict(item="ok item", critical=False, verdict="shown", confidence=0.9, vision="yes", description_says=True, kind="camera"))
    return Review(items=items, score=score, confidence=confidence, decision=decision, reasons=list(reasons))


def script(monkeypatch, *reviews):
    queue = list(reviews)

    async def fake_check(provider, image, plan, **kw):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(sr, "check_scene", fake_check)


def test_accepts_first_good_picture_in_one_attempt(tmp_path, monkeypatch):
    script(monkeypatch, review("accept", 1.0))
    eng = FakeEngine()
    r = generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k1", seed=7)
    assert len(eng.calls) == 1 and r.status == "accept" and r.unmet == [] and not r.unverified
    assert (tmp_path / r.image_path).exists() and (tmp_path / "panels" / "_candidates" / "k1" / "c001.png").exists()
    assert json.loads((tmp_path / "panels" / "k1.json").read_text())["status"] == "accept"


def test_failed_item_becomes_emphasis_next_attempt(tmp_path, monkeypatch):
    script(monkeypatch, review("regenerate", 0.3, failed=[STRIKE]), review("accept", 1.0))
    eng = FakeEngine()
    r = generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k2", seed=7)
    assert len(eng.calls) == 2 and eng.calls[1]["prompt"].startswith(f"Most important: {STRIKE}.")
    assert not eng.calls[0]["prompt"].startswith("Most important") and eng.calls[0]["seed"] != eng.calls[1]["seed"]
    assert r.status == "accept"


def test_stops_at_max_attempts_and_delivers_best_with_unmet(tmp_path, monkeypatch):
    script(monkeypatch, review("regenerate", 0.2, [STRIKE]), review("regenerate", 0.5, [STRIKE]), review("regenerate", 0.3, [STRIKE]))
    eng = FakeEngine()
    r = generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k3", seed=7, budget=SceneBudget(max_attempts=3, max_seconds=999))
    assert len(eng.calls) == 3 and r.status == "needs_review" and r.unmet == [STRIKE]
    assert r.review.score == 0.5  # the best of the three, not the last


def test_unreviewable_picture_is_delivered_unverified(tmp_path, monkeypatch):
    script(monkeypatch, RuntimeError("vision model down"))
    eng = FakeEngine()
    r = generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k4", seed=7)
    assert len(eng.calls) == 1 and r.unverified and r.status == "unverified" and (tmp_path / r.image_path).exists()


def test_all_uncertain_review_is_unverified_not_accepted(tmp_path, monkeypatch):
    script(monkeypatch, review("accept_low", 0.5, confidence=0.0, reasons=["unverified: the reviewer could not judge any item"]))
    r = generate_scene(FakeEngine(), None, fight_plan(), ws=tmp_path, key="k5", seed=7)
    assert r.unverified and r.status != "accept"


def test_cancel_stops_and_keeps_candidates(tmp_path, monkeypatch):
    script(monkeypatch, review("regenerate", 0.3, [STRIKE]))
    eng = FakeEngine()
    r = generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k6", seed=7, is_cancelled=lambda: len(eng.calls) >= 1)
    assert len(eng.calls) == 1 and "cancelled" in r.unmet
    assert (tmp_path / "panels" / "_candidates" / "k6" / "c001.png").exists() and (tmp_path / r.image_path).exists()


def test_cancel_before_any_picture_raises(tmp_path, monkeypatch):
    script(monkeypatch)
    with pytest.raises(RuntimeError, match="cancelled"):
        generate_scene(FakeEngine(), None, fight_plan(), ws=tmp_path, key="k7", seed=7, is_cancelled=lambda: True)


def test_time_budget_stops_the_loop_and_says_so(tmp_path, monkeypatch):
    script(monkeypatch, review("regenerate", 0.3, [STRIKE]), review("accept", 1.0))
    eng = FakeEngine()
    r = generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k8", seed=7, budget=SceneBudget(max_attempts=3, max_seconds=0.0))
    assert len(eng.calls) == 1 and "time budget used" in r.unmet and r.status == "needs_review"


def test_lessons_reach_the_negative_prompt(tmp_path, monkeypatch):
    script(monkeypatch, review("accept", 1.0))
    eng = FakeEngine()
    generate_scene(eng, None, fight_plan(), ws=tmp_path, key="k9", seed=7, lessons="both fighters on one side")
    assert "both fighters on one side" in eng.calls[0]["negative"]
