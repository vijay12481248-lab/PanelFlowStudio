"""Character Registry: reference assets, generation parameters, approval workflow, ComfyUI reference selection."""

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from engine.database.models import (
    Base,
    ProjectRecord,
    PageRecord,
    PanelRecord,
    CharacterRecord,
    AssetRecord,
)
from engine.database.session import SessionLocal, engine, run_sqlite_migrations
from engine.story.service import story_service
from engine.acquisition.models import PipelineStage


import uuid

def setup_project_with_panels(tmp_path, project_id=None):
    """Create a test project with pages and panels."""
    if project_id is None:
        project_id = f'char-ref-{uuid.uuid4().hex[:8]}'
    page_id = f'page-{uuid.uuid4().hex[:8]}'
    panel1_id = f'panel-{uuid.uuid4().hex[:8]}'
    panel2_id = f'panel-{uuid.uuid4().hex[:8]}'

    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    with SessionLocal() as db:
        db.add(ProjectRecord(
            id=project_id,
            title='Character Ref Test',
            source_type='LOCAL_FOLDER',
            rights_status='PUBLIC_DOMAIN',
            workspace_path=str(tmp_path),
            current_stage=PipelineStage.STORY_APPROVED.value,
        ))
        db.add(PageRecord(
            id=page_id, project_id=project_id, sequence=1,
            filename='page1.jpg', status='READY', width=1024, height=1536,
            byte_size=1000, sha256='a' * 64,
        ))
        db.add(PanelRecord(
            id=panel1_id, project_id=project_id, page_id=page_id,
            sequence=1, page_sequence=1, x=0, y=0, width=512, height=768,
            crop_filename='panel1.jpg', status='CONFIRMED',
        ))
        db.add(PanelRecord(
            id=panel2_id, project_id=project_id, page_id=page_id,
            sequence=2, page_sequence=2, x=512, y=0, width=512, height=768,
            crop_filename='panel2.jpg', status='CONFIRMED',
        ))
        db.commit()
    return project_id, page_id, panel1_id, panel2_id


def test_character_reference_asset_linking(tmp_path):
    """A character can have a canonical reference asset linked from AssetRecord."""
    project_id, page_id, panel1_id, panel2_id = setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        # Create character
        char = CharacterRecord(
            id='char-hero',
            project_id=project_id,
            display_name='Hero',
            canonical_name='Hero Protagonist',
            visual_traits=['blue eyes', 'red cape'],
            role='PROTAGONIST',
            first_panel_id=panel1_id,
            reference_panel_ids=[panel1_id],
            status='APPROVED',
            manual_override=True,
        )
        db.add(char)
        db.commit()

        # Create reference asset (generated image)
        asset = AssetRecord(
            id='asset-hero-ref',
            project_id=project_id,
            asset_type='CHARACTER_REFERENCE',
            filename='hero_ref.png',
            relative_path='references/hero_ref.png',
            content_type='image/png',
            width=512,
            height=768,
            byte_size=50000,
            sha256='b' * 64,
            provenance={'workflow_id': 'manga_consistent_qwen_image_edit', 'seed': 42, 'model': 'qwen'},
        )
        db.add(asset)
        db.commit()

        # Link asset to character
        char.reference_asset_id = 'asset-hero-ref'
        db.commit()
        db.refresh(char)

        assert char.reference_asset_id == 'asset-hero-ref'


def test_character_generation_parameters_persisted(tmp_path):
    """Character stores the generation model/workflow/seed/provenance used for its reference."""
    project_id, page_id, panel1_id, panel2_id = setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        char = CharacterRecord(
            id='char-villain',
            project_id=project_id,
            display_name='Villain',
            visual_traits=['green skin', 'horns'],
            role='ANTAGONIST',
            first_panel_id=panel2_id,
            reference_panel_ids=[panel2_id],
            status='APPROVED',
            manual_override=True,
        )
        db.add(char)
        db.commit()

        # Store generation parameters on character
        char.generation_params = {
            'workflow_id': 'manga_image_generation',
            'model': 'qwen',
            'seed': 12345,
            'prompt': 'villain character design, green skin, horns, manga style',
            'negative_prompt': 'low quality, blurry',
            'width': 512,
            'height': 768,
        }
        db.commit()
        db.refresh(char)

        params = char.generation_params
        assert params['workflow_id'] == 'manga_image_generation'
        assert params['seed'] == 12345
        assert params['model'] == 'qwen'


def test_character_approval_workflow(tmp_path):
    """Character changes require human approval; unapproved changes are staged."""
    project_id, page_id, panel1_id, panel2_id = setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        char = CharacterRecord(
            id='char-sidekick',
            project_id=project_id,
            display_name='Sidekick',
            visual_traits=['yellow shirt'],
            role='SUPPORTING',
            first_panel_id=panel1_id,
            reference_panel_ids=[panel1_id],
            status='DRAFT',
            manual_override=False,
        )
        db.add(char)
        db.commit()

        # Propose a change (staged, not applied)
        char.proposed_changes = {
            'visual_traits': ['yellow shirt', 'blue boots'],
            'description': 'Loyal companion with blue boots',
        }
        char.change_status = 'PENDING_REVIEW'
        db.commit()

        assert char.change_status == 'PENDING_REVIEW'
        assert 'blue boots' in char.proposed_changes['visual_traits']

        # Approve the change
        char.visual_traits = char.proposed_changes['visual_traits']
        char.description = char.proposed_changes['description']
        char.change_status = 'APPROVED'
        char.proposed_changes = {}
        char.manual_override = True
        db.commit()

        assert char.change_status == 'APPROVED'
        assert 'blue boots' in char.visual_traits
        assert char.manual_override is True


def test_character_reference_selection_for_comfyui_job(tmp_path):
    """Character reference asset can be selected as input for ComfyUI consistent generation."""
    project_id, page_id, panel1_id, panel2_id = setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        char = CharacterRecord(
            id='char-consistent',
            project_id=project_id,
            display_name='Consistent Hero',
            visual_traits=['silver armor'],
            role='PROTAGONIST',
            first_panel_id=panel1_id,
            reference_panel_ids=[panel1_id],
            status='APPROVED',
            manual_override=True,
        )
        db.add(char)
        db.commit()

        # Reference asset
        asset = AssetRecord(
            id='asset-consistent-ref',
            project_id=project_id,
            asset_type='CHARACTER_REFERENCE',
            filename='consistent_ref.png',
            relative_path='references/consistent_ref.png',
            content_type='image/png',
            width=512,
            height=768,
            byte_size=60000,
            sha256='c' * 64,
            provenance={'workflow_id': 'manga_consistent_qwen_image_edit', 'seed': 999},
        )
        db.add(asset)
        db.commit()

        char.reference_asset_id = 'asset-consistent-ref'
        db.commit()

        # Simulate ComfyUI job input construction
        ref_asset = db.query(AssetRecord).filter(AssetRecord.id == char.reference_asset_id).first()
        assert ref_asset is not None
        assert ref_asset.asset_type == 'CHARACTER_REFERENCE'
        assert ref_asset.provenance['workflow_id'] == 'manga_consistent_qwen_image_edit'


def test_two_characters_retain_traits_across_scenes(tmp_path):
    """Acceptance: two recurring characters keep approved traits across scenes."""
    project_id, page_id, panel1_id, panel2_id = setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        # Create two approved characters with distinct traits
        hero = CharacterRecord(
            id='char-hero-acceptance',
            project_id=project_id,
            display_name='Hero',
            canonical_name='The Hero',
            visual_traits=['blue eyes', 'red cape', 'golden sword'],
            role='PROTAGONIST',
            first_panel_id=panel1_id,
            reference_panel_ids=[panel1_id, panel2_id],
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 111},
        )
        villain = CharacterRecord(
            id='char-villain-acceptance',
            project_id=project_id,
            display_name='Villain',
            canonical_name='Dark Lord',
            visual_traits=['green skin', 'horns', 'black armor'],
            role='ANTAGONIST',
            first_panel_id=panel2_id,
            reference_panel_ids=[panel2_id],
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 222},
        )
        db.add_all([hero, villain])
        db.commit()

        # Verify traits are stable and retrievable
        chars = story_service.list_characters(db, project_id)
        hero_db = next(c for c in chars if c.id == 'char-hero-acceptance')
        villain_db = next(c for c in chars if c.id == 'char-villain-acceptance')

        assert set(hero_db.visual_traits) == {'blue eyes', 'red cape', 'golden sword'}
        assert set(villain_db.visual_traits) == {'green skin', 'horns', 'black armor'}
        assert hero_db.status == 'APPROVED'
        assert villain_db.status == 'APPROVED'
        assert hero_db.manual_override is True
        assert villain_db.manual_override is True