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
