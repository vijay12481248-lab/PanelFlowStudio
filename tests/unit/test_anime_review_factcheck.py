import asyncio

import pytest

from engine.anime.review import factcheck as fc
from engine.anime.review.models import Beat, EpisodeAnalysis, ReviewScript, ScriptSegment, Segment, Understanding

U = Understanding(summary="Sintel searches for a dragon called Scales.", characters=["Sintel", "Scales"], beats=[
    Beat(id="b01", start=0, end=9, kind="opening", label="An old man warns Sintel", why="w", visual="a man by a fire")])
A = EpisodeAnalysis(duration_sec=60, transcript=[Segment(start=1, end=3, text="You're a fool for traveling alone."),
                                                 Segment(start=4, end=6, text="I am looking for a dragon.")])
EV, DLG = fc.evidence_pack(U, A), fc.dialogue_evidence(A)


def issues(text, **kw):
    return fc.lexical_issues(text, EV, DLG, **kw)


def test_invented_kinship_word_flagged_but_evidenced_one_passes():
    assert any("sister" in i for i in issues("Sintel hunts for her sister, Scales."))
    assert not issues("Sintel hunts for a dragon, Scales.")


def test_invented_name_flagged_sentence_start_ignored():
    assert any("Asha" in i for i in issues("She meets Asha by the fire."))
    assert not issues("Honestly the pacing drags. Then Sintel arrives.")


def test_quotes_must_come_from_dialogue():
    assert not issues('He says "you\'re a fool for traveling alone" and she shrugs.')
    assert any("quoted line" in i for i in issues('She yells "we will burn it all down" at him.'))


def test_numbers_checked_except_where_exempt():
    assert any("number 7" in i for i in issues("It takes 7 days."))
    assert not issues("I rate it 9 out of 10.", check_numbers=False)


class Judge:
    def __init__(self, invented, rewrite="Sintel hunts for a dragon."):
        self.invented, self.rewrite, self.calls = invented, rewrite, []

    async def generate_structured(self, prompt, model, **kw):
        self.calls.append(model.__name__)
        if model is fc._Judgement:
            return model(invented=self.invented.pop(0) if self.invented else [])
        return model(text=self.rewrite)


def test_judge_echoes_of_evidence_are_discarded():
    p = Judge([["Scales is a dragon", "hunts for a dragon"]])
    out = asyncio.run(fc.judge(p, EV, "Sintel hunts for a dragon, and it looks great."))
    assert out == ["hunts for a dragon"]  # first phrase is not in the narration, so it is an echo


def test_lexical_failure_is_rewritten_and_llm_judge_skipped_on_it():
    p = Judge([[]])
    text, bad = asyncio.run(fc.check_text(p, EV, DLG, "Sintel hunts for her sister Scales today and always.", "recap"))
    assert bad == [] and "sister" not in text and p.calls[0] == "_Rewrite"


def test_required_segment_kept_with_flags_optional_dropped():
    sc = ReviewScript(title_hook="t", rating=7, segments=[
        ScriptSegment(id="s1", clip_id="c", role="hook", text="Sintel hunts for her sister today and always."),
        ScriptSegment(id="s2", clip_id="c", role="highlight", text="Sintel hunts for her sister today and always."),
        ScriptSegment(id="s3", clip_id="c", role="cta", text="What do you think of Sintel and the dragon Scales?")])
    stubborn = Judge([], rewrite="Still her sister is the one Sintel hunts for in these lands.")
    out = asyncio.run(fc.verify_script(sc, U, A, stubborn))
    assert [s.role for s in out.segments] == ["hook", "cta"] and [s.id for s in out.segments] == ["s1", "s2"]
    assert out.segments[0].flags and not out.segments[1].flags


def test_summary_falls_back_to_moments_when_ungroundable():
    u = U.model_copy(update={"summary": "Sintel hunts her sister Scales."})
    out = asyncio.run(fc.ground_summary(u, A, Judge([], rewrite="Her sister Scales is out there somewhere far away.")))
    assert "sister" not in out.summary and "old man" in out.summary.lower()
