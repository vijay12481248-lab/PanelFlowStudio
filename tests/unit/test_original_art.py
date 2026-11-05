import json
import asyncio
import io

from PIL import Image

from engine.original import art
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene


def story(genre="bedtime"):
    b = Bible(premise=Premise(title="T", genre=genre, logline="l", tone="t", setting="s"),
              characters=[Character(id="mira", name="Mira", role="protagonist", age_group="child",
                                    look="short brown hair, green eyes, yellow raincoat, red boots", personality="p"),
                          Character(id="pip", name="Pip", role="other", age_group="adult",
                                    look="small grey owl, round eyes, tiny scarf, soft feathers", personality="p")],
              locations=[Location(id="attic", name="Attic", look="dusty, wooden beams, warm lamp, round window")])
    panels = [Panel(id=f"p{i:03d}", scene_id="sc01", shot=s, angle=a, location_id="attic", character_ids=c,
                    action="Mira holds a lamp and smiles.", dialogue=[Line(speaker_id="mira", text="Hi")])
              for i, (s, a, c) in enumerate([("wide", "eye_level", []), ("close", "low", ["mira"]), ("medium", "high", ["mira", "pip"])], 1)]
    return OriginalStory(bible=b, scenes=[Scene(id="sc01", location_id="attic", character_ids=["mira"], summary="s", mood="m")], panels=panels)


def test_prompt_repeats_looks_style_shot_and_angle():
    s = story()
    pos, neg = art.build_prompt(s, s.panels[1])
    assert "solo" in pos and "yellow raincoat" in pos and "close-up" in pos and "from below" in pos and "storybook" in pos
    assert "dusty, wooden beams" in pos and "nsfw" in neg and "speech bubble" in neg
    pos3, _ = art.build_prompt(s, s.panels[2])
    assert "2others" in pos3 and "small grey owl" in pos3
    assert "no humans" in art.build_prompt(s, s.panels[0])[0]


def test_emphasis_wraps_missing_tags():
    s = story()
    pos, _ = art.build_prompt(s, s.panels[1], ["yellow raincoat"])
    assert "(yellow raincoat:1.3)" in pos


def test_seeds_are_stable_and_attempts_differ():
    s = story()
    assert art.seed_for(s, "p001") == art.seed_for(s, "p001") != art.seed_for(s, "p002")
    assert art.seed_for(s, "p001", 1) != art.seed_for(s, "p001", 0)


def png():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return buf.getvalue()


class FakeRunner:
    def __init__(self):
        self.calls = []

    def generate(self, pos, neg, seed, w, h, prefix, **kw):
        self.calls.append((prefix, seed, pos))
        return png()


class Vision:
    """Fails the first look at p003's characters, then passes."""

    def __init__(self, answers):
        self.answers, self.n = answers, 0

    async def analyze_vision(self, image, prompt, **kw):
        a = self.answers[min(self.n, len(self.answers) - 1)]
        self.n += 1
        return a


def test_generate_art_without_check_makes_sheets_and_panels_and_resumes(tmp_path):
    s, r = story(), FakeRunner()
    out = art.generate_art(s, tmp_path, r)
    assert out["generated"] == 3 and out["reused"] == 0 and len(r.calls) == 2 + 3  # 2 sheets + 3 panels
    assert (tmp_path / "sheets" / "mira.png").exists() and (tmp_path / "panels" / "p003.png").exists()
    r2 = FakeRunner()
    out2 = art.generate_art(s, tmp_path, r2)
    assert out2["generated"] == 0 and out2["reused"] == 3 and r2.calls == []  # nothing regenerated
    s.panels[1].action = "Mira opens the window."
    r3 = FakeRunner()
    assert art.generate_art(s, tmp_path, r3)["generated"] == 1 and len(r3.calls) == 1  # only the changed panel


def test_check_panel_scores_tags_and_treats_garbage_as_failure(tmp_path):
    s = story()
    img = tmp_path / "x.png"
    img.write_bytes(png())
    mira = s.bible.characters[0]
    tags = ["short brown hair", "green eyes", "yellow raincoat", "red boots"]
    ok = '{"results":[' + ",".join(f'{{"tag":"{x}","visible":{str(x != "red boots").lower()}}}' for x in tags) + "]}"
    score, missing = asyncio.run(art.check_panel(Vision([ok]), img, [mira]))
    assert score == 1.0 and missing == []  # only the 3 core tags are checked, "red boots" (the 4th) is not
    assert asyncio.run(art.check_panel(Vision(["not json"]), img, [mira]))[0] == 0.0
    assert asyncio.run(art.check_panel(Vision(['{"results":[]}']), img, [mira]))[0] == 0.0  # absent character: all tags unconfirmed
    miss = '{"results":[' + ",".join(f'{{"tag":"{x}","visible":{str(x != "green eyes").lower()}}}' for x in tags[:3]) + "]}"
    assert asyncio.run(art.check_panel(Vision([miss]), img, [mira]))[1] == ["green eyes"]
    two = '{"results":[{"tag":"short brown hair","visible":true},{"tag":"green eyes","visible":true}]}'
    assert asyncio.run(art.check_panel(Vision([two]), img, [mira], "extreme_close"))[0] == 1.0  # a close-up expects 2 tags


def test_panel_that_does_not_show_the_narration_is_regenerated_with_emphasis_and_best_kept(tmp_path):
    s = story()
    s.panels = s.panels[1:2]
    s.panels[0].key_visuals = ["eyes closed", "asleep"]
    tags = ["short brown hair", "green eyes"]  # a close-up checks the first two look tags
    ident = '{"results":[' + ",".join(f'{{"tag":"{x}","visible":true}}' for x in tags) + "]}"

    def match(seen):
        return '{"results":[' + ",".join(f'{{"tag":"{k}","visible":{str(k in seen).lower()}}}' for k in ("eyes closed", "asleep")) + "]}"

    r = FakeRunner()
    out = art.generate_art(s, tmp_path, r, provider=Vision([ident, match(set()), ident, match({"eyes closed", "asleep"})]))
    panel_calls = [c for c in r.calls if c[0].startswith("panel_")]
    assert len(panel_calls) == 2 and "(eyes closed:1.4)" in panel_calls[1][2] and panel_calls[0][1] != panel_calls[1][1]
    assert out["mean_match"] == 1.0 and out["below_threshold"] == []


def test_identity_score_alone_does_not_trigger_redraws(tmp_path):
    s = story()
    s.panels = s.panels[1:2]
    bad_identity = '{"results":[]}'
    r = FakeRunner()
    out = art.generate_art(s, tmp_path, r, provider=Vision([bad_identity]))
    assert len([c for c in r.calls if c[0].startswith("panel_")]) == 1 and out["mean_score"] == 0.0


def test_closed_eyes_and_back_views_lower_the_reference_pin():
    p = story().panels[1].model_copy(update={"key_visuals": ["eyes closed"], "action": "x"})
    assert art.pose_sensitive(p) and not art.pose_sensitive(p.model_copy(update={"key_visuals": ["smiling"], "action": "waves hello"}))


def test_first_character_reference_is_passed_when_ipadapter_is_available(tmp_path):
    class IpaRunner(FakeRunner):
        ipa = object()

        def generate(self, pos, neg, seed, w, h, prefix, reference=None, **kw):
            self.calls.append((prefix, seed, pos, reference))
            return png()

    s, r = story(), IpaRunner()
    art.generate_art(s, tmp_path, r)
    refs = {c[0]: c[3] for c in r.calls}
    assert refs["panel_p001"] is None  # no character on screen: nothing to pin
    assert refs["panel_p002"].name == "mira.png" and refs["panel_p003"].name == "mira.png"  # first character leads
    r2 = IpaRunner()
    art.generate_art(s, tmp_path, r2)
    assert r2.calls == []  # reference name is part of the cache key and unchanged


def test_two_character_panel_passes_both_references_to_the_masked_workflow(tmp_path):
    class Ipa2Runner(FakeRunner):
        ipa, ipa2 = object(), object()

        def generate(self, pos, neg, seed, w, h, prefix, reference=None, reference_b=None, **kw):
            self.calls.append((prefix, reference, reference_b))
            return png()

    r = Ipa2Runner()
    art.generate_art(story(), tmp_path, r)
    refs = {c[0]: (c[1], c[2]) for c in r.calls}
    assert refs["panel_p003"][0].name == "mira.png" and refs["panel_p003"][1].name == "pip.png"  # two on screen: left=Mira, right=Pip
    assert refs["panel_p002"][1] is None  # one character: single reference only


def test_closed_eyes_requirement_is_weighted_and_open_eyes_are_negated():
    s = story()
    p = s.panels[1].model_copy(update={"key_visuals": ["eyes closed", "sleeping"]})
    pos, neg = art.build_prompt(s, p)
    assert "(eyes closed:1.4)" in pos and "(sleeping:1.4)" in pos and "open eyes" in neg
    assert "open eyes" not in art.build_prompt(s, s.panels[1])[1]


class Reviewer:
    """Fake models for the reviewer: claims, a vision model answering numbered questions, and a description judge."""

    def __init__(self, good_from_attempt=1, always_no=False):
        self.attempt, self.good_from, self.always_no = 0, good_from_attempt, always_no

    async def generate_structured(self, prompt, model, **kw):
        from engine.original import review as rv
        if model is rv._Claims:
            return model(claims=[{"text": "her eyes are closed", "critical": True}])
        if model is rv._DescJudge:
            ok = (self.attempt >= self.good_from) and not self.always_no
            return model(stated=[ok] * 10)
        raise AssertionError(model)

    async def analyze_vision(self, image, prompt, **kw):
        from engine.original import review as rv
        if "format_schema" in kw:
            self.attempt += 1
            ok = (self.attempt - 1 >= self.good_from) and not self.always_no
            return json.dumps({"answers": [{"n": i + 1, "answer": "yes" if ok or i > 0 else "no", "evidence": "eyes open" if not ok else "eyes shut"}
                                           for i in range(10)]})
        return "a girl lying down with her eyes shut" if self.attempt >= self.good_from else "a girl lying down looking at the viewer"


def directed_panel(s):
    from engine.original.shotspec import CharPose, ShotSpec

    return s.panels[1].model_copy(update={"director": ShotSpec(
        shot="close", camera="eye_level", setting="a dusty attic with a round window", lighting="lamp light", mood="calm", key_visuals=["eyes closed"],
        characters=[CharPose(id="mira", side="center", pose="lying down", expression="eyes closed", action="")]).model_dump(),
        "key_visuals": ["eyes closed"], "caption": "Mira lies down and her eyes are closed."})


def test_picture_is_reviewed_against_the_narration_and_redrawn_until_accepted(tmp_path):
    s = story()
    s.panels = [directed_panel(s)]
    r = FakeRunner()
    out = art.generate_art(s, tmp_path, r, provider=Reviewer(good_from_attempt=1))
    calls = [c for c in r.calls if c[0].startswith("panel_")]
    assert len(calls) == 2 and "her eyes are closed" in calls[1][2]  # the miss the reviewer reported is weighted into the retry
    rec = json.loads((tmp_path / "art.json").read_text())[0]
    assert rec["status"] == "accept" and rec["review"]["decision"] == "accept" and rec["claims"][0]["text"] == "her eyes are closed"
    assert out["accepted"] == [rec["panel_id"]] and out["needs_review"] == []
    assert "eyes shut" in rec["description"] and (tmp_path / "review_report.html").exists()


def test_a_picture_that_never_matches_is_marked_needs_review_not_silently_accepted(tmp_path):
    s = story()
    s.panels = [directed_panel(s)]
    r = FakeRunner()
    out = art.generate_art(s, tmp_path, r, provider=Reviewer(always_no=True))
    assert len([c for c in r.calls if c[0].startswith("panel_")]) == art.DIRECTED_ATTEMPTS  # every attempt was used
    rec = json.loads((tmp_path / "art.json").read_text())[0]
    assert rec["status"] == "needs_review" and out["needs_review"] == [rec["panel_id"]] and out["below_threshold"] == out["needs_review"]
    assert "critical item not shown: her eyes are closed" in rec["review"]["reasons"]
    assert "needs_review" in (tmp_path / "review_report.html").read_text(encoding="utf-8")

def test_a_prompt_following_engine_gets_sentences_and_no_negative_prompt(tmp_path):
    from engine.original.shotspec import CharPose, ShotSpec

    class FluxRunner(FakeRunner):
        style, engine = "natural", "flux"

        def generate(self, pos, neg, seed, w, h, prefix, **kw):
            self.calls.append((prefix, seed, pos, neg))
            return png()

    s = story()
    s.panels = [s.panels[1].model_copy(update={"director": ShotSpec(
        shot="medium", setting="a dusty attic", lighting="lamp light", mood="calm", key_visuals=["a glowing lamp"],
        characters=[CharPose(id="mira", side="center", pose="standing", expression="smiling", action="holding a lamp")]).model_dump()})]
    r = FluxRunner()
    art.generate_art(s, tmp_path, r)
    panel = [c for c in r.calls if c[0].startswith("panel_")][0]
    assert "The picture must clearly show: a glowing lamp." in panel[2] and panel[3] == ""
    sheet = [c for c in r.calls if c[0].startswith("sheet_")][0]
    assert sheet[2].startswith("Character reference portrait") and sheet[3] == ""
    assert json.loads((tmp_path / "art.json").read_text())[0]["prompt_hash"]


def test_review_decisions_two_witnesses_agree_or_confidence_drops():
    from engine.original import review as rv
    qa = lambda *a: [rv._QA(n=i + 1, answer=x, evidence="e") for i, x in enumerate(a)]
    reqs = [("a silver bell hangs on the wall", True), ("exactly 1 person is visible", True), ("a corridor", False)]
    good = rv.combine(reqs, qa("yes", "yes", "yes"), [True, True, True])
    assert good.decision == "accept" and good.score == 1.0 and good.confidence == 0.9
    assert rv.combine(reqs, qa("no", "yes", "yes"), [False, True, True]).decision == "regenerate"  # critical object missing, both agree
    split = rv.combine(reqs, qa("yes", "yes", "yes"), [False, False, False])  # vision says yes, the description never mentions it
    assert split.decision == "accept_low" or split.confidence < 0.6
    unclear = rv.combine(reqs, qa("partly", "yes", "yes"), [True, True, True])
    assert unclear.decision == "accept_low" and any("unclear" in r for r in unclear.reasons)  # half-shown critical item: kept but flagged, and the loop still retries (rank 1 < accept)
    assert rv.combine([], [], []).decision == "accept_low"


def test_requirements_come_from_the_narration_then_the_shot_spec():
    from engine.original import review as rv
    from engine.original.shotspec import CharPose, ShotSpec

    s = story()
    spec = ShotSpec(shot="medium", setting="The corridor: long hallway. Peeling paint", characters=[CharPose(id="mira", pose="standing", expression="x", action="y")])
    reqs = rv.requirements([rv.Claim(text="a silver bell hangs high on the wall", critical=True)], spec, {c.id: c for c in s.bible.characters})
    assert reqs[0] == ("a silver bell hangs high on the wall", True)
    assert ("exactly 1 person or creature is visible", True) in reqs and any("short brown hair" in t for t, _ in reqs)
    assert rv.requirements([], ShotSpec(shot="wide"), {})[0] == ("there are no people in the picture", True)


def test_last_attempt_widens_the_frame_and_front_loads_what_was_missed():
    from engine.original.shotspec import CharPose, ShotSpec

    s = story()
    p = s.panels[1].model_copy(update={"director": ShotSpec(shot="medium", characters=[CharPose(id="mira", pose="standing", expression="calm", action="looking up")],
                                                            setting="a hall").model_dump()})
    first, _ = art.build_prompt(s, p, style="natural", attempt=0)
    last, _ = art.build_prompt(s, p, ["a silver bell on the wall"], "natural", must=["a silver bell on the wall"], attempt=2)
    assert "Medium shot" in first and "Wide shot" in last
    assert last.startswith("Most important: the picture must clearly show a silver bell on the wall.")


def test_claims_are_positive_visible_statements_from_this_narration():
    from engine.original import review as rv

    narration = "Elena turns her head upward, her eyes locking onto the single silver bell hanging high on the wall."
    claims = [rv.Claim(text="a single silver bell hangs high on the wall"), rv.Claim(text="Elena Vance is present"),
              rv.Claim(text="there is no visible sign of the date"), rv.Claim(text="an adult woman with messy black hair"),
              rv.Claim(text="her head is turned upward", critical=True), rv.Claim(text="a single silver bell hangs high on the wall")]
    kept = [c.text for c in rv.clean_claims(claims, narration)]
    assert kept == ["a single silver bell hangs high on the wall", "her head is turned upward"]  # no names, no negations, no cast parroting, no duplicates


def test_flux_uses_pulid_when_character_reference_is_provided(tmp_path):
    from unittest.mock import MagicMock
    from pathlib import Path
    
    mock_client = MagicMock()
    mock_client.base_url = 'http://127.0.0.1:8188/'
    mock_client.submit_prompt.return_value = 'pid123'
    mock_client.history.return_value = {'pid123': {'outputs': {'7': {'images': [{'filename': 'out.png', 'subfolder': '', 'type': 'output'}]}}}}
    mock_client.download_output.return_value = b'fakepng'
    
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = mock_client
    runner.engine = 'flux'
    runner.style = 'natural'
    mock_inputs = {'text': '', 'neg': '', 'seed': 0, 'w': 100, 'h': 100, 'p': ''}
    runner.flux = ({'1': {'class_type': 'TestNode', 'inputs': mock_inputs.copy()}}, {'patch_slots': {'prompt': {'node_id': '1', 'input': 'text', 'class_type': 'TestNode'}, 'negative_prompt': {'node_id': '1', 'input': 'neg', 'class_type': 'TestNode'}, 'seed': {'node_id': '1', 'input': 'seed', 'class_type': 'TestNode'}, 'width': {'node_id': '1', 'input': 'w', 'class_type': 'TestNode'}, 'height': {'node_id': '1', 'input': 'h', 'class_type': 'TestNode'}, 'filename_prefix': {'node_id': '1', 'input': 'p', 'class_type': 'TestNode'}}})
    runner.flux_pulid = ({'1': {'class_type': 'TestNode', 'inputs': mock_inputs.copy()}, '8': {'class_type': 'LoadImage', 'inputs': {'image': ''}}, '12': {'class_type': 'ApplyPulidFlux', 'inputs': {'weight': 0.85}}}, {'patch_slots': {'prompt': {'node_id': '1', 'input': 'text', 'class_type': 'TestNode'}, 'negative_prompt': {'node_id': '1', 'input': 'neg', 'class_type': 'TestNode'}, 'seed': {'node_id': '1', 'input': 'seed', 'class_type': 'TestNode'}, 'width': {'node_id': '1', 'input': 'w', 'class_type': 'TestNode'}, 'height': {'node_id': '1', 'input': 'h', 'class_type': 'TestNode'}, 'filename_prefix': {'node_id': '1', 'input': 'p', 'class_type': 'TestNode'}, 'reference_image': {'node_id': '8', 'input': 'image', 'class_type': 'LoadImage'}, 'reference_weight': {'node_id': '12', 'input': 'weight', 'class_type': 'ApplyPulidFlux'}}})
    runner.ipa = None
    runner.ipa2 = None
    runner._upload = lambda p: 'uploaded_' + p.name
    
    ref_file = tmp_path / 'char.png'
    ref_file.write_bytes(b'abc')
    
    # 1. With reference -> uses flux_pulid
    runner.generate('hero portrait', '', 42, 1344, 768, 'test', reference=ref_file)
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    assert '8' in submitted_wf and submitted_wf['8']['inputs']['image'] == 'uploaded_char.png'
    
    # 2. Without reference -> uses flux_schnell
    mock_client.reset_mock()
    runner.generate('landscape view', '', 42, 1344, 768, 'test', reference=None)
    submitted_wf2 = mock_client.submit_prompt.call_args[0][0]
    assert '8' not in submitted_wf2
