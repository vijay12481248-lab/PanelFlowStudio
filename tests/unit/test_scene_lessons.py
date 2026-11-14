"""Task 8 of the scene-director plan: lessons learned from failed checks (temp ledger files only)."""
from pathlib import Path

from engine.creative.mistakes import MistakeLedger
from engine.original.models import ItemVerdict, Review
from engine.original.scene_lessons import lesson_domain, lessons_for, record_outcome

MODEL = "qwen_image_21"


def item(text, kind, passed=False, evidence="not visible"):
    return ItemVerdict(item=text, critical=True, verdict="shown" if passed else "missing", confidence=0.9, vision="yes" if passed else "no",
                       description_says=passed, kind=kind, evidence=evidence)


def rev(*items):
    return Review(items=list(items), score=0.5, confidence=0.9, decision="regenerate")


def ledger(tmp_path):
    return MistakeLedger(file_path=tmp_path / "scene_lessons.json")


STRIKE_A = "an adult man with short black hair, scarred cheek, worn blue coat is striking"
STRIKE_B = "a teenage girl with silver braid, green cloak, wooden staff is striking"


def test_one_failure_is_recorded_but_not_a_lesson(tmp_path):
    led = ledger(tmp_path)
    assert record_outcome(led, MODEL, "fight", rev(item(STRIKE_A, "pose"))) == 1
    assert lessons_for(led, MODEL, "fight") == ""
    assert len(led.load_mistakes(lesson_domain(MODEL, "fight"))) == 1  # kept, waiting for a second sighting


def test_second_identical_failure_becomes_a_lesson(tmp_path):
    led = ledger(tmp_path)
    record_outcome(led, MODEL, "fight", rev(item(STRIKE_A, "pose")))
    record_outcome(led, MODEL, "fight", rev(item(STRIKE_B, "pose")))  # a different story and characters, the same failure
    text = lessons_for(led, MODEL, "fight")
    assert "fully extended" in text
    entries = led.load_mistakes(lesson_domain(MODEL, "fight"))
    assert len(entries) == 1 and entries[0].recurrence_count == 2


def test_story_specific_words_never_reach_the_ledger(tmp_path):
    led = ledger(tmp_path)
    record_outcome(led, MODEL, "fight", rev(item(STRIKE_A, "pose", evidence="the scarred cheek man stands still")))
    blob = (tmp_path / "scene_lessons.json").read_text(encoding="utf-8")
    assert "scarred" not in blob and "blue coat" not in blob


def test_lessons_are_per_model_and_scene_type(tmp_path):
    led = ledger(tmp_path)
    for _ in range(2):
        record_outcome(led, MODEL, "fight", rev(item(STRIKE_A, "pose")))
    assert lessons_for(led, MODEL, "fight")
    assert lessons_for(led, MODEL, "emotion") == ""
    assert lessons_for(led, "minimax_h3_image_edit", "fight") == ""


def test_passed_items_write_nothing(tmp_path):
    led = ledger(tmp_path)
    assert record_outcome(led, MODEL, "fight", rev(item(STRIKE_A, "pose", passed=True))) == 0
    assert led.load_mistakes(lesson_domain(MODEL, "fight")) == []


def test_camera_failure_maps_to_the_camera_rule(tmp_path):
    led = ledger(tmp_path)
    for _ in range(2):
        record_outcome(led, MODEL, "fight", rev(item("the camera looks up at the scene from a low angle", "camera")))
    assert "steeply upward" in lessons_for(led, MODEL, "fight")


def test_count_placement_and_contact_failures_each_get_a_rule(tmp_path):
    led = ledger(tmp_path)
    failures = [item("exactly two figures are in the picture", "subject"),
                item("an adult man with a is on the left of the picture", "placement"),
                item("an adult man with a reaches an adult man with b with the sword, aimed down-right", "pose")]
    for _ in range(2):
        assert record_outcome(led, MODEL, "fight", rev(*failures)) == 3
    text = lessons_for(led, MODEL, "fight")
    assert "exactly the stated number" in text and "exactly on the side" in text and "visibly touches" in text


def test_unknown_item_kinds_are_ignored_not_crashed(tmp_path):
    led = ledger(tmp_path)
    assert record_outcome(led, MODEL, "fight", rev(item("the main light comes from above", "environment"))) == 0


def test_only_the_given_ledger_file_is_touched(tmp_path):
    repo_default = Path("engine/chronoflow/vault/mistakes_ledger.json")
    before = repo_default.stat().st_mtime_ns if repo_default.exists() else None
    led = ledger(tmp_path)
    record_outcome(led, MODEL, "fight", rev(item(STRIKE_A, "pose")))
    assert (repo_default.stat().st_mtime_ns if repo_default.exists() else None) == before
    assert (tmp_path / "scene_lessons.json").exists()
