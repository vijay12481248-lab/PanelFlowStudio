"""
Unit tests for the script and prompt direction sanitizer.
Verifies stripping of stage directions, acting cues, speaker attributions,
and prompt leakage before speech synthesis.
"""
import pytest
from engine.audio.sanitizer import clean_script_text, detect_prompt_leakage


def test_strip_bracketed_stage_directions():
    text = "[whisper] Do not move. [sigh] They are watching us. [gasp]"
    cleaned = clean_script_text(text)
    assert cleaned == "Do not move. They are watching us."


def test_strip_parenthetical_acting_cues():
    text = "(whispering) The seal is broken. (sighs deeply) We must retreat."
    cleaned = clean_script_text(text)
    assert cleaned == "The seal is broken. We must retreat."


def test_strip_asterisk_actions():
    text = "*steps forward cautiously* I accept your challenge. *smiles*"
    cleaned = clean_script_text(text)
    assert cleaned == "I accept your challenge."


def test_strip_speaker_prefixes():
    examples = [
        ("Protagonist: The battle has only just begun.", "The battle has only just begun."),
        ("The Narrator: Long ago, the realm was united.", "Long ago, the realm was united."),
        ("Marcus: Stand firm!", "Stand firm!"),
        ("Grandmaster Gu: We shall meet again.", "We shall meet again."),
        ("Zhuo Fan: Interesting.", "Interesting."),
    ]
    for raw, expected in examples:
        assert clean_script_text(raw) == expected


def test_strip_scene_and_panel_prefixes():
    examples = [
        ("Scene 1 — Panel #1: Dawn broke over the horizon.", "Dawn broke over the horizon."),
        ("Panel 2: A shadow loomed in the doorway.", "A shadow loomed in the doorway."),
        ("Shot 3 - The sword clashed against stone.", "The sword clashed against stone."),
    ]
    for raw, expected in examples:
        assert clean_script_text(raw) == expected


def test_dummy_label_produces_empty_string():
    assert clean_script_text("Scene 1 — Panel #1.") == ""
    assert clean_script_text("Panel #3.") == ""
    assert clean_script_text("Scene 2") == ""


def test_strip_trailing_stage_attributions():
    # Real leaked examples from Chapter 925
    s1 = '"Standing in the courtyard, the two characters exchange final words about reporting their findings. Grandmaster Gu signals his departure as the chapter concludes." Protagonist exclaims, refusing to yield an inch.'
    assert clean_script_text(s1) == "Standing in the courtyard, the two characters exchange final words about reporting their findings. Grandmaster Gu signals his departure as the chapter concludes."

    s2 = '"I will report to the Sect Master immediately!" Grandmaster Gu signals solemnly.'
    assert clean_script_text(s2) == "I will report to the Sect Master immediately!"

    s3 = "We must prepare the defenses! he shouted urgently."
    assert clean_script_text(s3) == "We must prepare the defenses!"


def test_preserves_spoken_action_sentences_in_narration():
    text = "The discussion turns to locating the 'Soaring Sword' at Jade Falls. Yifan shouts an intense declaration that their surprise attack will succeed."
    assert clean_script_text(text) == text
    assert clean_script_text("He stands beside the doorway.") == "He stands beside the doorway."


def test_detect_prompt_leakage():
    # Prompt leakage cases
    leaked_1 = "Protagonist: Zero dialogue, seven panels of pure flex—this page screams 'sit down' without saying a word."
    is_leak, reason = detect_prompt_leakage(leaked_1)
    assert is_leak is True
    assert "silent" in reason.lower() or "meta-commentary" in reason.lower()

    leaked_2 = "Grandmaster Gu signals his departure as the chapter concludes."
    is_leak, reason = detect_prompt_leakage(leaked_2)
    assert is_leak is True
    assert "chapter" in reason.lower() or "stage direction" in reason.lower()

    # Normal narration should NOT be flagged as leakage
    valid_text = "The cold wind swept across the mountain peaks as the scouts returned."
    is_leak, _ = detect_prompt_leakage(valid_text)
    assert is_leak is False
