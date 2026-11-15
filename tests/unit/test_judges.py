"""Task 1 of the review-page plan: two vision judges with one answer shape (fake provider and fake ComfyUI client, no GPU)."""
import asyncio

import pytest

from engine.original import judges as jd
from engine.original.judges import ComfyJudge, JudgeAnswer, OllamaJudge, available_judges, parse_judge_text, read_prompt, reread_prompt

STATES = ["striking", "blocking", "readying", "struck", "falling", "dodging", "other"]
REAL = "CAMERA: Level with them.  \nPEOPLE: Two people.  \nACTIONS: Left: Punching forward. Right: Blocking with hands."


def run(coro):
    return asyncio.run(coro)


def test_parse_real_qwen3vl_text():
    a = parse_judge_text(REAL, "qwen3-vl-8b", STATES)
    assert a.ok and a.camera == "level" and a.people == 2 and a.actions == ["punching", "blocking"]


@pytest.mark.parametrize("phrase,expected", [
    ("looking up from below", "looks_up"), ("looks_up", "looks_up"), ("Looking UP at them", "looks_up"),
    ("from above", "looks_down"), ("looks_down", "looks_down"), ("looking down on them", "looks_down"),
    ("tilted sideways", "tilted"), ("Level", "level"), ("eye level", "level"),
])
def test_parse_camera_phrases(phrase, expected):
    assert parse_judge_text(f"CAMERA: {phrase}\nPEOPLE: 1\nACTIONS: standing", "j", STATES).camera == expected


@pytest.mark.parametrize("phrase,expected", [("Two people.", 2), ("2", 2), ("one person", 1), ("a single man", 1), ("no people", 0), ("There are three.", 3), ("zero", 0)])
def test_parse_people_words_and_digits(phrase, expected):
    assert parse_judge_text(f"CAMERA: level\nPEOPLE: {phrase}\nACTIONS: x", "j", STATES).people == expected


def test_actions_are_mapped_to_an_allowed_state_by_stem_else_kept():
    a = parse_judge_text("CAMERA: level\nPEOPLE: 2\nACTIONS: strikes; blocking\nEVIDENCE: the left arm is extended", "j", STATES)
    assert a.actions == ["striking", "blocking"] and a.evidence == "the left arm is extended"
    b = parse_judge_text("CAMERA: level\nPEOPLE: 1\nACTIONS: 1. Dancing wildly", "j", STATES)
    assert b.actions == ["dancing"]


@pytest.mark.parametrize("text", ["", "   ", "The image shows two men fighting in a courtyard.", "I cannot help with that."])
def test_parse_unusable_text_is_not_ok(text):
    a = parse_judge_text(text, "j", STATES)
    assert not a.ok and a.camera is None and a.people is None and a.actions == []


def test_read_prompt_never_mentions_a_plan():
    p = read_prompt(STATES).lower()
    assert "plan" not in p and "hero" not in p and "villain" not in p and "striking" in p and "camera:" in p and "people:" in p and "actions:" in p


def test_reread_prompt_contains_the_other_claim_and_asks_for_evidence():
    p = reread_prompt("camera", None, "looks_up", "the horizon sits below the faces", STATES)
    assert "looks_up" in p and "the horizon sits below the faces" in p and "evidence" in p.lower() and "do not assume" in p.lower()
    q = reread_prompt("action", 1, "blocking", "arms raised", STATES)
    assert "second person from the left" in q.lower() or "person 2" in q.lower()


class FakeClient:
    def __init__(self, text=REAL, status="success", raise_on=None, catalog=None, models=None, never_done=False):
        self.text, self.status, self.raise_on, self.never_done = text, status, raise_on, never_done
        self.catalog = {"TextGenerate": {}} if catalog is None else catalog
        self.models = {"text_encoders": ["qwen3vl_8b_int8_convrot.safetensors"]} if models is None else models
        self.submitted, self.uploads = [], []

    def upload_image_bytes(self, data, filename=None):
        if self.raise_on == "upload":
            raise RuntimeError("upload failed")
        self.uploads.append(len(data))
        return "pf_x.png"

    def submit_prompt(self, workflow, client_id=None):
        if self.raise_on == "submit":
            raise RuntimeError("ComfyUI is offline")
        self.submitted.append(workflow)
        return "pid-1"

    def history(self, pid):
        if self.never_done:
            return {}
        return {pid: {"status": {"completed": self.status == "success", "status_str": self.status}, "outputs": {"4": {"text": [self.text]}} if self.status == "success" else {}}}

    def node_catalog(self):
        return self.catalog

    def discover_models(self):
        return self.models


def test_comfy_graph_has_the_four_nodes_and_flag_values():
    g = ComfyJudge(FakeClient()).build_graph("pf_x.png", "Q?")
    assert [g[k]["class_type"] for k in ("1", "2", "3", "4")] == ["LoadImage", "CLIPLoader", "TextGenerate", "PreviewAny"]
    assert g["1"]["inputs"]["image"] == "pf_x.png"
    assert g["2"]["inputs"] == {"clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}
    assert g["3"]["inputs"]["sampling_mode"] == "off" and g["3"]["inputs"]["thinking"] is False and g["3"]["inputs"]["prompt"] == "Q?"
    assert g["3"]["inputs"]["clip"] == ["2", 0] and g["3"]["inputs"]["image"] == ["1", 0] and g["4"]["inputs"]["source"] == ["3", 0]


def test_comfy_judge_reads_text_from_history_output(tmp_path):
    client = FakeClient()
    pic = tmp_path / "p.png"
    pic.write_bytes(b"\x89PNG fake")
    a = run(ComfyJudge(client, poll_s=0).read(pic, STATES))
    assert a.ok and a.judge == "qwen3-vl-8b" and a.camera == "level" and a.people == 2 and client.uploads == [len(b"\x89PNG fake")]
    assert client.submitted[0]["3"]["inputs"]["prompt"].startswith("Look at the picture")


@pytest.mark.parametrize("client", [FakeClient(raise_on="upload"), FakeClient(raise_on="submit"), FakeClient(status="error"), FakeClient(never_done=True)])
def test_comfy_judge_error_or_timeout_is_not_ok_not_raised(client):
    a = run(ComfyJudge(client, poll_s=0, timeout_s=0.05).read(b"png", STATES))
    assert not a.ok and a.judge == "qwen3-vl-8b"


class FakeProvider:
    def __init__(self, text=REAL, error=None):
        self.text, self.error, self.calls = text, error, []

    async def analyze_vision(self, image, prompt, **kw):
        self.calls.append((prompt, kw))
        if self.error:
            raise self.error
        return self.text


def test_ollama_judge_reads_and_never_raises():
    prov = FakeProvider()
    a = run(OllamaJudge(prov).read(b"png", STATES))
    assert a.ok and a.judge == "qwen3.5:9b" and prov.calls[0][1]["temperature"] == 0.0
    bad = run(OllamaJudge(FakeProvider(error=ConnectionError("down"))).read(b"png", STATES))
    assert not bad.ok


def test_reread_returns_the_single_value_asked_for():
    prov = FakeProvider("CAMERA: looks_up\nEVIDENCE: faces seen from below")
    other = JudgeAnswer(judge="x", ok=True, camera="level", people=2, actions=["a", "b"], evidence="flat horizon")
    a = run(OllamaJudge(prov).reread(b"png", "camera", None, other, STATES))
    assert a.camera == "looks_up" and a.evidence == "faces seen from below"
    assert "level" in prov.calls[0][0] and "flat horizon" in prov.calls[0][0]


def test_available_judges_without_textgenerate_is_ollama_only():
    judges = run(available_judges(FakeProvider(), FakeClient(catalog={})))
    assert [j.name for j in judges] == ["qwen3.5:9b"]


def test_available_judges_needs_the_model_file_too():
    assert [j.name for j in run(available_judges(FakeProvider(), FakeClient(models={"text_encoders": []})))] == ["qwen3.5:9b"]


def test_available_judges_with_both():
    assert [j.name for j in run(available_judges(FakeProvider(), FakeClient()))] == ["qwen3.5:9b", "qwen3-vl-8b"]


def test_available_judges_never_raises_when_comfyui_is_down():
    class Down(FakeClient):
        def node_catalog(self):
            raise ConnectionError("down")

    assert [j.name for j in run(available_judges(FakeProvider(), Down()))] == ["qwen3.5:9b"]


def test_a_reply_with_only_an_actions_line_is_usable():
    # real bake-off finding: the re-look for one person's action answers with ACTIONS + EVIDENCE only, and was thrown away as unusable
    a = parse_judge_text("ACTIONS: blocking\nEVIDENCE: both arms are raised in front of the chest", "j", STATES)
    assert a.ok and a.actions == ["blocking"] and a.camera is None and a.people is None



@pytest.mark.parametrize("reply,expected", [
    ("ACTIONS: The second person is blocking", ["blocking"]),
    ("ACTIONS: left person striking; right person blocking", ["striking", "blocking"]),
    ("ACTIONS: not striking", ["unclear"]),
])
def test_action_words_must_be_states_not_sentence_fragments(reply, expected):
    # review finding I1: "The second person is blocking" used to parse as ["second"] and then come out "agreed"
    assert parse_judge_text("CAMERA: level\nPEOPLE: 2\n" + reply, "j", STATES).actions == expected


@pytest.mark.parametrize("reply,expected", [
    ("close-up at eye level", "level"), ("looking straight down from above", "looks_down"), ("not looking up, it is level", "level"),
    ("the camera is not tilted, it looks down", "looks_down"), ("seven people, even ground", None), ("looks_up", "looks_up"),
])
def test_camera_words_are_not_matched_inside_other_words_or_negations(reply, expected):
    assert parse_judge_text(f"CAMERA: {reply}\nPEOPLE: 1\nACTIONS: standing", "j", STATES).camera == expected


@pytest.mark.parametrize("reply,expected", [("1 woman and 2 men", None), ("no more than two", None), ("The other reviewer said 3 but I count 2", None), ("no people", 0), ("Two people.", 2)])
def test_people_count_must_be_one_clear_number(reply, expected):
    assert parse_judge_text(f"CAMERA: level\nPEOPLE: {reply}\nACTIONS: standing", "j", STATES).people == expected


def test_a_judge_echoing_the_question_template_is_not_a_usable_answer():
    echoed = parse_judge_text(read_prompt(STATES), "j", STATES)
    assert not echoed.ok and echoed.camera is None and echoed.people is None and echoed.actions == []


def test_reread_of_one_person_takes_that_persons_word_from_a_full_list():
    from engine.original.judges import item_value

    full = JudgeAnswer(judge="j", ok=True, actions=["striking", "falling"])
    assert item_value(full, "action", 1, reread=True) == "falling"
    assert item_value(JudgeAnswer(judge="j", ok=True, actions=["blocking"]), "action", 1, reread=True) == "blocking"
    assert item_value(full, "action", 2, reread=True) is None
