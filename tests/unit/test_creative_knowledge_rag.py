"""Unit tests for PanelFlow Creative Studio Hybrid RAG Knowledge Base."""

import pytest
from pathlib import Path
from engine.creative.knowledge import CreativeKnowledgeBase
from engine.creative.schema import KnowledgeCategory, KnowledgeEntry


@pytest.fixture
def temp_kb(tmp_path: Path) -> CreativeKnowledgeBase:
    """Provide an isolated CreativeKnowledgeBase instance backed by a temporary SQLite file."""
    db_file = tmp_path / "test_kb.db"
    return CreativeKnowledgeBase(db_path=db_file)


def test_kb_initialization_and_default_seeds(temp_kb: CreativeKnowledgeBase):
    """Verify tables are created and default foundational wisdom entries are seeded."""
    entries = temp_kb.list_entries(limit=50)
    assert len(entries) >= 6

    titles = [e.title for e in entries]
    assert any("Vertical" in t and "Scroll" in t for t in titles)
    assert any("Cultivation" in t for t in titles)
    assert any("Kinetic" in t for t in titles)
    assert any("Cliffhanger" in t or "Climax" in t for t in titles)


def test_kb_add_and_retrieve_entry(temp_kb: CreativeKnowledgeBase):
    """Verify adding a new atomic knowledge entry and retrieving it by ID."""
    entry = KnowledgeEntry(
        entry_id="kb_test_001",
        category=KnowledgeCategory.ACTION_CHOREOGRAPHY,
        title="Three-Beat Sword Clash Rhythm",
        content="In high-speed martial arts sequences, clash arcs should follow anticipation (60px), impact flash (20px), and recoil silence (140px).",
        tags=["swordsmanship", "choreography", "recoil", "impact"],
        source="unit_test",
        confidence_score=0.95,
    )
    temp_kb.add_entry(entry)

    retrieved = temp_kb.get_entry("kb_test_001")
    assert retrieved is not None
    assert retrieved.title == "Three-Beat Sword Clash Rhythm"
    assert retrieved.category == KnowledgeCategory.ACTION_CHOREOGRAPHY
    assert "swordsmanship" in retrieved.tags
    assert retrieved.confidence_score == 0.95


def test_kb_fts5_bm25_search(temp_kb: CreativeKnowledgeBase):
    """Verify fast BM25 full-text keyword retrieval across content and tags."""
    # Query for cultivation-related terms
    results = temp_kb.query("spiritual aura dao", limit=5)
    assert len(results) > 0
    assert any("Cultivation" in r.title or "Spiritual" in r.content for r in results)

    # Query for gutter timing terms
    results_gutter = temp_kb.query("gutter rhythm timing scroll", limit=5)
    assert len(results_gutter) > 0
    assert any("Gutter" in r.title or "Gutter" in r.content or "Vertical" in r.title for r in results_gutter)


def test_kb_category_filter(temp_kb: CreativeKnowledgeBase):
    """Verify category-specific filtering during queries."""
    cat_entries = temp_kb.query(
        "visual composition",
        category=KnowledgeCategory.PANEL_COMPOSITION,
        limit=5,
    )
    for entry in cat_entries:
        assert entry.category == KnowledgeCategory.PANEL_COMPOSITION

    dialogue_entries = temp_kb.list_entries(category=KnowledgeCategory.DIALOGUE_AND_SFX)
    for entry in dialogue_entries:
        assert entry.category == KnowledgeCategory.DIALOGUE_AND_SFX


def test_kb_update_existing_entry(temp_kb: CreativeKnowledgeBase):
    """Verify that adding an entry with an existing ID updates it without duplication."""
    entry1 = KnowledgeEntry(
        entry_id="kb_upd_01",
        category=KnowledgeCategory.GENERAL,
        title="Original Title",
        content="Initial content text.",
        tags=["tag1"],
    )
    temp_kb.add_entry(entry1)

    entry2 = KnowledgeEntry(
        entry_id="kb_upd_01",
        category=KnowledgeCategory.GENERAL,
        title="Updated Title",
        content="Refined content text with enhanced insights.",
        tags=["tag1", "tag2"],
    )
    temp_kb.add_entry(entry2)

    retrieved = temp_kb.get_entry("kb_upd_01")
    assert retrieved is not None
    assert retrieved.title == "Updated Title"
    assert "Refined" in retrieved.content

    # Query should reflect updated content
    search_res = temp_kb.query("Refined")
    assert any(r.entry_id == "kb_upd_01" for r in search_res)


def test_kb_delete_entry(temp_kb: CreativeKnowledgeBase):
    """Verify deleting an entry purges it from relational table and FTS index."""
    entry = KnowledgeEntry(
        entry_id="kb_del_01",
        category=KnowledgeCategory.GENERAL,
        title="To Be Deleted",
        content="Ephemeral content to purge.",
        tags=["temporary"],
    )
    temp_kb.add_entry(entry)
    assert temp_kb.get_entry("kb_del_01") is not None

    deleted = temp_kb.delete_entry("kb_del_01")
    assert deleted is True
    assert temp_kb.get_entry("kb_del_01") is None
    assert len(temp_kb.query("Ephemeral")) == 0
