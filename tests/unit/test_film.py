"""Film stage: H3 frame grid, shot spec rules, motion prompts, and the integrity of the authored Dawn Gate story."""
import importlib.util
from pathlib import Path

import pytest

from engine.original import film
from engine.original.models import OriginalStory

SRC = Path(__file__).resolve().parents[2] / "stories" / "dawn_gate_source.py"


@pytest.fixture(scope="module")
def story() -> OriginalStory:
    spec = importlib.util.spec_from_file_location("dawn_gate_source", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.story


def test_snap_frames_lands_on_the_17k_plus_5_grid():
    for s in (0.1, 0.9, 2.3, 3.0, 3.75, 4.5, 5.9, 7.2):
        n = film.snap_frames(s)
        assert n % 17 == 5 and n >= round(s * 24) and n - round(s * 24) < 17
    assert film.snap_frames(3.75) == 90 and film.snap_frames(2.3) == 56


def test_line_rate_shouts_faster_and_hesitations_slower():
    assert film.line_rate("Run!", 1.0) > 1.0 > film.line_rate("I... don't know.", 1.0)
    assert film.line_rate("Fine.", 1.0) == 1.0


def test_every_shot_has_one_speaker_who_is_in_frame_and_every_spec_is_complete(story):
    ids = [p.id for p in story.panels]
    assert len(ids) == len(set(ids))
    cast = {c.id for c in story.bible.characters}
    for p in story.panels:
        assert len(p.dialogue) <= 1, f"{p.id}: one speaker per shot so one voice is anchored to one face"
        assert p.motion.strip(), f"{p.id}: a shot with nothing moving is a still"
        spec = film.film_spec(story, p)
        assert len(spec.characters) <= 3 and {c.id for c in spec.characters} <= cast
        if p.dialogue:
            speaker = next((c for c in spec.characters if c.id == p.dialogue[0].speaker_id), None)
            assert speaker is not None and "mouth" in speaker.expression
            assert len(p.dialogue[0].text) <= 130, f"{p.id}: a long line makes a long, static clip"


def test_pip_never_speaks_and_every_scene_has_a_score(story):
    assert all(ln.speaker_id != "pip" for p in story.panels for ln in p.dialogue)
    assert all(s.score and s.bpm and s.key for s in story.scenes)


def test_motion_prompt_describes_motion_only_and_routes_sound(story):
    talk = next(p for p in story.panels if p.dialogue)
    silent = next(p for p in story.panels if not p.dialogue)
    t, s = film.motion_prompt(story, talk), film.motion_prompt(story, silent)
    assert talk.dialogue[0].text in t and "exact sync" in t and "only the spoken voice" in t
    assert "no speech" in s and "says:" not in s
    assert "non_diegetic_music: none" in t and "non_diegetic_music: none" in s
    assert "copper-red" not in t  # the picture carries the look; re-describing it makes faces melt


def test_film_workflows_are_registered_with_matching_checksums():
    import hashlib
    import json

    root = Path(film.__file__).resolve().parents[1] / "comfyui"
    reg = {w["id"]: w for w in json.loads((root / "workflow_registry.json").read_text(encoding="utf-8"))}
    for wid in (film.FREE_ID, film.VOICE_ID):
        raw = (root / "workflows" / reg[wid]["filename"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == reg[wid]["sha256"]
        g = json.loads(raw)
        assert g["105:91"]["inputs"]["fps"] == 24
    assert "voice_audio" in reg[film.VOICE_ID]["patch_slots"] and "voice_audio" not in reg[film.FREE_ID]["patch_slots"]
