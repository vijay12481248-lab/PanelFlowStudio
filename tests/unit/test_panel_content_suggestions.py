from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
import pytest

from engine.database.models import Base, ProjectRecord, TextRegionRecord
from engine.api.routers.panels import panel_content_suggestions


def test_suggestions_respect_project_and_corrected_text():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p", title="Test", source_type="LOCAL_FOLDER", workspace_path="test", rights_status="PUBLIC_DOMAIN"))
        for identifier, project, raw, corrected in [
            ("promo", "p", "Visit our website example.com", ""),
            ("dialogue", "p", "Run!", ""),
            ("corrected", "p", "example.com", "Come back soon!"),
            ("other", "other-project", "example.com", ""),
        ]:
            db.add(TextRegionRecord(id=identifier, project_id=project, page_id="page", panel_id="panel",
                                    x=10, y=20, width=100, height=30, raw_text=raw, corrected_text=corrected))
        db.commit()
        result = panel_content_suggestions("p", db)
        assert result["regions_checked"] == 3
        assert [item["region_id"] for item in result["suggestions"]] == ["promo"]
        assert result["suggestions"][0]["bbox"] == [10, 20, 100, 30]
        assert result["ocr_required"] is False
        with pytest.raises(HTTPException) as error:
            panel_content_suggestions("missing", db)
        assert error.value.status_code == 404


def test_empty_project_requests_ocr():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p", title="Test", source_type="LOCAL_FOLDER", workspace_path="test", rights_status="PUBLIC_DOMAIN"))
        db.commit()
        assert panel_content_suggestions("p", db)["ocr_required"] is True


def test_custom_labels_persist_and_match_ocr_spacing():
    from engine.api.routers.panels import save_content_labels, PromotionalLabelsRequest
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p", title="Test", source_type="LOCAL_FOLDER", workspace_path="test", rights_status="PUBLIC_DOMAIN"))
        db.add(TextRegionRecord(id="promo", project_id="p", page_id="page", panel_id="panel",
                               x=0, y=0, width=100, height=20, raw_text="Watch on MANHUU PLUS . COM"))
        db.commit()
        save_content_labels("p", PromotionalLabelsRequest(labels=["ManhuuPlus.com", ""]), db)
        result = panel_content_suggestions("p", db)
        assert result["labels"] == ["manhuuplus.com"]
        assert [r["region_id"] for r in result["suggestions"]] == ["promo"]
        db.get(TextRegionRecord, "promo").status = "BLURRED"
        db.commit()
        assert panel_content_suggestions("p", db)["suggestions"] == []


def test_labels_are_literal_and_empty_labels_never_match():
    from engine.imaging.sanitizer import matches_label
    assert not matches_label("ordinary dialogue", ["", ".*", "   "])
    assert matches_label("Read on Manhuu Plus.com", ["ManhuuPlus.com"])
