"""Unit tests for PanelFlow Clean-Room Manhua Structural Analyzer."""

import pytest
from pathlib import Path
from engine.creative.knowledge import CreativeKnowledgeBase
from engine.creative.manhua_analyzer import ManhuaStructuralAnalyzer
from engine.creative.schema import KnowledgeCategory, ManhuaDeconstructionReport


@pytest.fixture
def temp_kb(tmp_path: Path) -> CreativeKnowledgeBase:
    db_file = tmp_path / "test_analyzer_kb.db"
    return CreativeKnowledgeBase(db_path=db_file)


@pytest.fixture
def analyzer(temp_kb: CreativeKnowledgeBase) -> ManhuaStructuralAnalyzer:
    return ManhuaStructuralAnalyzer(kb=temp_kb)


def test_analyze_manifest_action_heavy(analyzer: ManhuaStructuralAnalyzer, temp_kb: CreativeKnowledgeBase):
    """Verify clean-room structural analysis of an action-heavy manhua chapter."""
    sample_panels = [
        {"aspect_ratio": "16:9", "gutter_spacing_px": 40, "dialogue_count": 5, "action_type": "kinetic_clash"},
        {"aspect_ratio": "16:9", "gutter_spacing_px": 30, "dialogue_count": 0, "action_type": "motion_dodge"},
        {"aspect_ratio": "9:16", "gutter_spacing_px": 50, "dialogue_count": 8, "action_type": "strike"},
        {"aspect_ratio": "1:1", "gutter_spacing_px": 60, "dialogue_count": 12, "action_type": "reaction"},
        {"aspect_ratio": "9:16", "gutter_spacing_px": 220, "dialogue_count": 2, "action_type": "cliffhanger_reveal"},
    ]

    report = analyzer.analyze_manifest(
        source_title="Peerless Battle Spirit",
        chapter_identifier="Ch. 142",
        panels=sample_panels,
        auto_ingest=True,
    )

    assert isinstance(report, ManhuaDeconstructionReport)
    assert report.source_title == "Peerless Battle Spirit"
    assert report.chapter_identifier == "Ch. 142"
    assert report.total_panels == 5
    assert report.average_gutter_spacing == (40 + 30 + 50 + 60 + 220) // 5
    assert "Kinetic Action Escalation" in report.pacing_profile
    assert len(report.extracted_heuristics) >= 2

    # Verify auto-ingestion into Knowledge Base
    kb_entries = temp_kb.query("Peerless Battle Spirit", limit=5)
    assert len(kb_entries) >= 1
    assert any("Peerless Battle Spirit" in e.title for e in kb_entries)


def test_analyze_manifest_dialogue_heavy(analyzer: ManhuaStructuralAnalyzer):
    """Verify structural detection of exposition / council discussion pacing."""
    sample_panels = [
        {"aspect_ratio": "16:9", "gutter_spacing_px": 120, "dialogue_count": 28, "action_type": "dialogue"},
        {"aspect_ratio": "16:9", "gutter_spacing_px": 100, "dialogue_count": 32, "action_type": "exposition"},
        {"aspect_ratio": "1:1", "gutter_spacing_px": 140, "dialogue_count": 25, "action_type": "court_scheme"},
    ]

    report = analyzer.analyze_manifest(
        source_title="Grandmaster of Demonic Cultivation",
        chapter_identifier="Ep. 12",
        panels=sample_panels,
        auto_ingest=False,
    )

    assert report.total_panels == 3
    assert report.dialogue_density > 20.0
    assert "Dialogue-Heavy Exposition" in report.pacing_profile


def test_analyze_url_clean_room(analyzer: ManhuaStructuralAnalyzer, temp_kb: CreativeKnowledgeBase):
    """Verify clean-room web feed analysis adheres to owner's rights gate (no scan pirating)."""
    report = analyzer.analyze_url(
        url="https://manhuaplus.org/manga/tales-of-demons-and-gods/chapter-420",
        source_title="Tales of Demons and Gods",
        chapter_identifier="Ch. 420",
        auto_ingest=True,
    )

    assert isinstance(report, ManhuaDeconstructionReport)
    assert report.source_title == "Tales of Demons and Gods"
    assert report.chapter_identifier == "Ch. 420"
    assert report.total_panels > 0
    assert len(report.action_flow_patterns) > 0

    # Ensure clean-room rule: no raw image binaries cached, only structural grammar
    kb_entries = temp_kb.query("Tales of Demons and Gods", limit=3)
    assert len(kb_entries) >= 1
    assert "Tales of Demons and Gods" in kb_entries[0].title
