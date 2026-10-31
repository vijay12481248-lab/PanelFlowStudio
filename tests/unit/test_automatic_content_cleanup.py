from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.database.models import Base, ProjectRecord, PageRecord, PanelRecord, TextRegionRecord
from engine.imaging import content_cleanup as cleanup
from engine.ocr.providers.base import OCRRegion, RawOCRResult


def region(text="Read first at ManhuaPlus.com", bbox=None, confidence=0.95):
    return OCRRegion(id="ocr", detected_text=text, bbox=bbox or [5, 5, 180, 20], confidence=confidence)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup.settings, "app_data_dir", tmp_path / "app")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for pid in ("first", "next-episode"):
            ws = tmp_path / pid
            (ws / "panels").mkdir(parents=True)
            db.add(ProjectRecord(id=pid, title=pid, source_type="LOCAL_FOLDER", workspace_path=str(ws), rights_status="PUBLIC_DOMAIN"))
            db.add(PageRecord(id=pid, project_id=pid, sequence=1, filename="page.png", width=900, height=1000))
        db.commit()
        yield db


def panel(db, pid="first", width=900, height=150):
    p = PanelRecord(id=pid, project_id=pid, page_id=pid, sequence=1, page_sequence=1,
                    x=0, y=0, width=width, height=height, crop_filename="panel.png")
    db.add(p)
    path = Path(db.get(ProjectRecord, pid).workspace_path) / "panels/panel.png"
    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).text((5, 5), "Read first at ManhuaPlus.com", fill="black")
    image.save(path)
    db.commit()
    return p, path


class OCR:
    engine_id = "test_real_contract"
    calls = 0

    def __init__(self, regions):
        self.regions = regions

    def is_available(self):
        return True

    def extract_text(self, path, panel_id):
        self.calls += 1
        return RawOCRResult(panel_id=panel_id, engine_id=self.engine_id, regions=self.regions)


def test_shared_labels_apply_to_two_independent_episodes(setup):
    cleanup.save_rules(cleanup.CleanupRules(labels=["example site"]))
    for pid in ("first", "next-episode"):
        p, path = panel(setup, pid)
        original = path.read_bytes()
        result = cleanup.cleanup_detected_panels(setup, pid, [p.id], ocr_engine=OCR([region("EXAMPLE SITE")]))
        assert result["items"][0]["action"] == "EXCLUDE"
        assert p.status == "IGNORED"
        assert path.read_bytes() == original
        assert setup.query(TextRegionRecord).filter_by(panel_id=p.id).one().status == "IGNORED"


def test_story_panel_is_preserved_local_text_blurred_and_rerun_is_idempotent(setup):
    p, path = panel(setup, height=800)
    original = path.read_bytes()
    ocr = OCR([region(), region("Run away!", [100, 300, 200, 40])])
    result = cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=ocr)
    assert result["items"][0]["action"] == "BLUR"
    assert p.status != "IGNORED"
    assert path.read_bytes() != original
    assert (path.parent / ".originals" / path.name).read_bytes() == original
    cleaned = path.read_bytes()
    cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=ocr)
    assert ocr.calls == 1
    assert path.read_bytes() == cleaned


@pytest.mark.parametrize("regions", [
    [region(confidence=0.3)],
    [region(bbox=[0, 0, 900, 800])],
])
def test_unreliable_matches_do_not_modify_image(setup, regions):
    p, path = panel(setup, height=800)
    original = path.read_bytes()
    result = cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=OCR(regions))
    assert result["items"][0]["action"] == "KEEP"
    assert path.read_bytes() == original
    assert p.status != "IGNORED"


def test_box_slightly_outside_panel_is_clamped_and_blurred():
    result = cleanup.decide_cleanup(900, 800, [region("Join our Discord", bbox=[-5, 0, 100, 20])],
                                    cleanup.CleanupRules().labels)
    assert result["action"] == "BLUR"
    assert result["regions"][0].bbox == [0, 0, 95, 20]


def test_unlisted_scanlator_domain_is_blurred():
    regions = [region("READ FIRST AT", [1452, 4966, 358, 48]), region("MANGACULTIVATOR.COM", [1362, 5035, 551, 46]),
               region("Run away!", [100, 300, 200, 40])]
    result = cleanup.decide_cleanup(1920, 6000, regions, labels=[])
    assert result["action"] == "BLUR"
    assert sorted(r.detected_text for r in result["regions"]) == ["MANGACULTIVATOR.COM", "READ FIRST AT"]


def test_stamp_header_also_covers_unread_logo_line():
    # OCR reads the white header but not the red/black logo below it (Magic Emperor 928, panel #28).
    result = cleanup.decide_cleanup(1920, 6018, [region("READ FIRST AT", [1451, 827, 358, 48]),
                                                 region("Run away!", [100, 300, 200, 40])], labels=[])
    x, y, w, h = result["regions"][0].bbox
    assert result["action"] == "BLUR"
    assert x <= 1362 and x + w >= 1909 and y <= 827 and y + h >= 827 + 69 + 46  # logo line: 69 px down, 46 tall


def test_detector_watermark_is_blurred_when_ocr_reads_nothing(setup):
    p, path = panel(setup, height=800)
    original = path.read_bytes()
    project = setup.get(ProjectRecord, "first")
    project.settings = {"detected_promos": {p.id: [[0, 0, 200, 25]]}}  # over the drawn stamp text
    setup.commit()
    result = cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=OCR([region("Run away!")]))
    assert result["items"][0]["action"] == "BLUR"
    assert path.read_bytes() != original and p.status != "IGNORED"


def test_credits_cover_is_excluded():
    regions = [region("TL: SU"), region("PR: SU"), region("CH 927"), region("Story text here")]
    assert cleanup.decide_cleanup(1920, 3000, regions, labels=[])["action"] == "EXCLUDE"


def test_dialogue_in_wide_panel_prevents_exclusion():
    result = cleanup.decide_cleanup(900, 150, [region(), region("Take cover!", [300, 30, 200, 40])], cleanup.CleanupRules().labels)
    assert result["action"] == "BLUR"


def test_cover_and_outro_artwork_are_excluded():
    result = cleanup.decide_cleanup(1920, 3000, [region("Head over to our website"),
                                    region("Support us")], cleanup.CleanupRules().labels)
    assert result["action"] == "EXCLUDE"
    result = cleanup.decide_cleanup(1920, 3000, [region("Updates in real time"),
                                    region("discord.gg/hello")], cleanup.CleanupRules().labels)
    assert result["action"] == "EXCLUDE"


def test_no_match_and_disabled_rules_preserve_panels(setup):
    p, path = panel(setup)
    original = path.read_bytes()
    ocr = OCR([region("Stay here!")])
    assert cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=ocr)["items"][0]["action"] == "KEEP"
    cleanup.save_rules(cleanup.CleanupRules(enabled=False))
    assert cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=ocr)["enabled"] is False
    assert path.read_bytes() == original


def test_mock_ocr_cannot_silently_claim_success(setup):
    p, _ = panel(setup)
    ocr = OCR([])
    ocr.engine_id = "mock_ocr"
    with pytest.raises(RuntimeError, match="requires real OCR"):
        cleanup.cleanup_detected_panels(setup, "first", [p.id], ocr_engine=ocr)


def legacy_review(db, p):
    """A NEEDS_REVIEW match left by the earlier cleanup policy, which can still exist in projects."""
    db.add(TextRegionRecord(id="legacy", project_id=p.project_id, page_id=p.page_id, panel_id=p.id,
                            x=5, y=5, width=180, height=20, raw_text="Read first at ManhuaPlus.com",
                            raw_confidence=0.2, ocr_engine="test", sequence_global=1,
                            detection_method="AUTO_CLEANUP", status="NEEDS_REVIEW"))
    project = db.get(ProjectRecord, p.project_id)
    project.settings = {"content_cleanup_report": {"panels": {p.id: {
        "panel_id": p.id, "action": "REVIEW", "reason": "Uncertain OCR or text covers too much artwork"}}}}
    db.commit()


def test_uncertain_cleanup_blocks_story_until_verified(setup):
    p, _ = panel(setup, height=800)
    legacy_review(setup, p)
    with pytest.raises(ValueError, match="uncertain promotional"):
        cleanup.require_cleanup_review(setup, "first")
    setup.query(TextRegionRecord).one().status = "CONFIRMED"
    setup.commit()
    cleanup.require_cleanup_review(setup, "first")


def test_page_detection_invokes_cleanup_before_returning(setup, monkeypatch):
    from engine.projects.service import project_service, panel_detector
    from engine.imaging.panels import PanelBox
    from engine.ocr.providers.registry import ocr_registry
    page = setup.get(PageRecord, "first")
    page.status = "READY"
    setup.commit()
    box = PanelBox(id="detected", page_id=page.id, sequence=1, page_sequence=1,
                   x=0, y=0, width=900, height=150)
    monkeypatch.setattr(panel_detector, "detect_panels", lambda *a, **k: [box])
    monkeypatch.setattr(panel_detector, "extract_crop", lambda src, b, dest: Image.new("RGB", (900, 150), "white").save(dest))
    monkeypatch.setattr(ocr_registry, "get_default_engine", lambda: OCR([region()]))
    panels = project_service.detect_panels_page(setup, "first", "first")
    assert len(panels) == 1
    assert panels[0].status == "IGNORED"
    assert setup.get(ProjectRecord, "first").settings["content_cleanup_report"]["panels"]["detected"]["action"] == "EXCLUDE"


def test_episode_detection_job_invokes_cleanup(setup, monkeypatch):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from engine.database import session
    from engine.projects.service import project_service, panel_detector
    from engine.imaging.panels import PanelBox
    from engine.ocr.providers.registry import ocr_registry
    page = setup.get(PageRecord, "next-episode")
    page.status = "READY"
    setup.commit()
    box = PanelBox(id="episode-panel", page_id=page.id, sequence=1, page_sequence=1,
                   x=0, y=0, width=900, height=150)
    monkeypatch.setattr(session, "SessionLocal", sessionmaker(bind=setup.get_bind()))
    monkeypatch.setattr(panel_detector, "detect_panels", lambda *a, **k: [box])
    monkeypatch.setattr(panel_detector, "extract_crop", lambda src, b, dest: Image.new("RGB", (900, 150), "white").save(dest))
    monkeypatch.setattr(ocr_registry, "get_default_engine", lambda: OCR([region()]))
    operation = project_service.detect_panels_project(setup, "next-episode", operation_only=True)
    asyncio.run(operation(SimpleNamespace(is_cancelled=False), lambda *args: None))
    setup.expire_all()
    assert setup.get(PanelRecord, "episode-panel").status == "IGNORED"


def test_autopilot_auto_resolves_promotional_cleanup(setup):
    from engine.pipeline.autopilot import AutoPilotRunner
    p, _ = panel(setup, height=800)
    legacy_review(setup, p)
    with pytest.raises(ValueError, match="uncertain promotional"):
        cleanup.require_cleanup_review(setup, "first")

    runner = AutoPilotRunner(project_id="first")
    project = setup.get(ProjectRecord, "first")
    runner._resolve_promotional_cleanup(setup, project)

    # Review requirement is now satisfied
    cleanup.require_cleanup_review(setup, "first")
    setup.expire_all()
    tr = setup.query(TextRegionRecord).filter_by(panel_id=p.id).one()
    assert tr.status == "IGNORED"
    assert setup.get(PanelRecord, p.id).status == "IGNORED"

