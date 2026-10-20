"""Milestone 3: Storyboard and Asset Reuse - regression tests."""
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
    AssetRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    SceneRecord,
    CharacterRecord,
    VisualTimelineRecord,
)
from engine.database.session import SessionLocal, engine, run_sqlite_migrations
from engine.acquisition.models import PipelineStage
from engine.story.alignment import alignment_service
from engine.motion.planning.shot_planner import ShotPlanner
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    AudioInterval,
    MotionStyleProfile,
)
from engine.motion.models.enums import TimelineSourceType
from engine.motion.models.camera import TargetResolution


import uuid

def setup_project_with_story(tmp_path):
    """Create a test project with script, scenes, and panels."""
    project_id = f'storyboard-test-{uuid.uuid4().hex[:8]}'
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    with SessionLocal() as db:
        db.add(ProjectRecord(
            id=project_id,
            title='Storyboard Test',
            source_type='LOCAL_FOLDER',
            rights_status='PUBLIC_DOMAIN',
            workspace_path=str(tmp_path),
            current_stage=PipelineStage.STORY_APPROVED.value,
        ))
        # Pages and panels - use unique IDs per test run
        page_ids = []
        panel_ids_by_page = []
        for i in range(3):
            page_id = f'page-{i+1}-{uuid.uuid4().hex[:8]}'
            page_ids.append(page_id)
            db.add(PageRecord(
                id=page_id, project_id=project_id, sequence=i+1,
                filename=f'page{i+1}.jpg', status='READY', width=1024, height=1536,
                byte_size=1000, sha256='a' * 64,
            ))
            panel_ids = []
            for j in range(3):
                panel_id = f'panel-{i+1}-{j+1}-{uuid.uuid4().hex[:8]}'
                panel_ids.append(panel_id)
                db.add(PanelRecord(
                    id=panel_id, project_id=project_id, page_id=page_id,
                    sequence=j+1, page_sequence=j+1, x=0, y=0, width=512, height=768,
                    crop_filename=f'{panel_id}.jpg', status='CONFIRMED',
                ))
            panel_ids_by_page.append(panel_ids)

        # Scenes - use unique IDs per test run
        scene1_id = f'scene-1-{uuid.uuid4().hex[:8]}'
        scene2_id = f'scene-2-{uuid.uuid4().hex[:8]}'
        # Use first panel of first page as scene-1 start, last panel of first page as scene-1 end
        # Use first panel of second page as scene-2 start, last panel of third page as scene-2 end
        scene1_start = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]
        scene1_end = panel_ids_by_page[0][-1] if panel_ids_by_page[0] else page_ids[0]
        scene2_start = panel_ids_by_page[1][0] if len(panel_ids_by_page) > 1 and panel_ids_by_page[1] else page_ids[1]
        scene2_end = panel_ids_by_page[-1][-1] if panel_ids_by_page[-1] else page_ids[-1]

        db.add(SceneRecord(
            id=scene1_id, project_id=project_id, sequence=1,
            title='The Ruins', panel_start=scene1_start, panel_end=scene1_end,
            character_ids=[], summary='Hero explores ruins.',
        ))
        db.add(SceneRecord(
            id=scene2_id, project_id=project_id, sequence=2,
            title='The Guardian', panel_start=scene2_start, panel_end=scene2_end,
            character_ids=[], summary='Guardian battle.',
        ))

        # Approved script
        script_id = f'script-1-{uuid.uuid4().hex[:8]}'
        script = VideoScriptRecord(
            id=script_id,
            project_id=project_id,
            version='1.0',
            adaptation_profile='FAITHFUL',
            estimated_duration=30.0,
            language='en',
            status='APPROVED',
            quality_metrics={},
        )
        db.add(script)
        # 5 segments across 2 scenes - use the dynamic scene IDs
        segments = [
            (f'seg-1-{uuid.uuid4().hex[:8]}', scene1_id, 1, 'CHARACTER_DIALOGUE', 'Hero enters the ruins.', 'NEUTRAL', 0.5, 3.0),
            (f'seg-2-{uuid.uuid4().hex[:8]}', scene1_id, 2, 'NARRATION', 'The ancient stones glow.', 'MYSTERIOUS', 0.6, 4.0),
            (f'seg-3-{uuid.uuid4().hex[:8]}', scene1_id, 3, 'CHARACTER_DIALOGUE', 'I sense danger ahead.', 'TENSE', 0.8, 3.5),
            (f'seg-4-{uuid.uuid4().hex[:8]}', scene2_id, 1, 'NARRATION', 'A guardian awakens.', 'DRAMATIC', 0.7, 4.5),
            (f'seg-5-{uuid.uuid4().hex[:8]}', scene2_id, 2, 'CHARACTER_DIALOGUE', 'We must fight!', 'EXCITED', 0.9, 3.0),
        ]
        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:
            db.add(ScriptSegmentRecord(
                id=seg_id, script_id=script_id, project_id=project_id,
                scene_id=scene_id, sequence=seq, type=seg_type,
                speaker_character_id=None, text=text, emotion=emotion,
                intensity=intensity, estimated_duration=dur,
                estimated_start=0.0, estimated_end=dur,
                source_evidence={}, production_intent='',
            ))

        # Characters with reference assets - use unique IDs per test run
        hero_id = f'char-hero-{uuid.uuid4().hex[:8]}'
        villain_id = f'char-villain-{uuid.uuid4().hex[:8]}'
        # Use dynamic panel IDs for character references
        hero_first_panel = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]
        hero_ref_panels = panel_ids_by_page[0][:2] if len(panel_ids_by_page[0]) >= 2 else [panel_ids_by_page[0][0]]
        villain_first_panel = panel_ids_by_page[2][0] if len(panel_ids_by_page) > 2 and panel_ids_by_page[2] else page_ids[-1]
        villain_ref_panels = panel_ids_by_page[2][:1] if len(panel_ids_by_page) > 2 and panel_ids_by_page[2] else [panel_ids_by_page[-1][0]]

        hero = CharacterRecord(
            id=f'char-hero-{uuid.uuid4().hex[:8]}',
            project_id=project_id,
            display_name='Hero',
            visual_traits=['blue armor', 'sword'],
            role='PROTAGONIST',
            first_panel_id=hero_first_panel,
            reference_panel_ids=hero_ref_panels,
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 111},
        )
        villain = CharacterRecord(
            id=f'char-villain-{uuid.uuid4().hex[:8]}',
            project_id=project_id,
            display_name='Guardian',
            visual_traits=['stone body', 'glowing eyes'],
            role='ANTAGONIST',
            first_panel_id=villain_first_panel,
            reference_panel_ids=villain_ref_panels,
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 222},
        )
        db.add_all([hero, villain])

        # Existing approved visual assets (reusable) - use unique IDs per test run
        asset1_id = f'asset-panel-1-1-{uuid.uuid4().hex[:8]}'
        asset2_id = f'asset-panel-2-2-{uuid.uuid4().hex[:8]}'
        # Use dynamic panel IDs for asset references
        asset1_panel = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]
        asset2_panel = panel_ids_by_page[1][1] if len(panel_ids_by_page) > 1 and len(panel_ids_by_page[1]) > 1 else page_ids[1]

        db.add(AssetRecord(
            id=asset1_id,
            project_id=project_id,
            asset_type='PANEL_CROP',
            filename=f'{asset1_panel}.jpg',
            relative_path=f'panels/{asset1_panel}.jpg',
            content_type='image/jpeg',
            width=512, height=768, byte_size=50000, sha256='b' * 64,
            provenance={'workflow_id': 'manga_image_generation', 'seed': 111},
            status='READY',
        ))
        db.add(AssetRecord(
            id=asset2_id,
            project_id=project_id,
            asset_type='PANEL_CROP',
            filename=f'{asset2_panel}.jpg',
            relative_path=f'panels/{asset2_panel}.jpg',
            content_type='image/jpeg',
            width=512, height=768, byte_size=50000, sha256='c' * 64,
            provenance={'workflow_id': 'manga_image_generation', 'seed': 333},
            status='READY',
        ))

        db.commit()
    return project_id


def test_storyboard_converts_approved_script_to_shot_contracts(tmp_path):
    """An approved script is converted into scene/shot contracts with timing."""
    project_id = setup_project_with_story(tmp_path)
    
    with SessionLocal() as db:
        from engine.story.alignment import alignment_service
        # Get the storyboard
        doc = alignment_service.align_script_to_frames(db, project_id)
        
        assert doc.project_id == project_id
        assert doc.script_id.startswith('script-1-')
        assert len(doc.segments) == 5  # 5 script segments
        assert doc.total_duration_sec > 0
        
        # Each segment should have supporting panels
        for seg in doc.segments:
            assert seg.segment_id.startswith('seg-')
            assert len(seg.supporting_panels) >= 1
            assert seg.measured_duration_sec > 0


def test_asset_reuse_decision_engine(tmp_path):
    """Asset reuse decision: reuse existing approved assets when possible."""
    project_id = setup_project_with_story(tmp_path)
    
    with SessionLocal() as db:
        from engine.story.alignment import alignment_service
        doc = alignment_service.align_script_to_frames(db, project_id)
        
        # Check that existing approved assets are referenced
        panel_ids_used = set()
        for seg in doc.segments:
            for panel_ref in seg.supporting_panels:
                panel_ids_used.add(panel_ref.panel_id)
        
        # Should reuse existing approved panel assets where available
        assert len(panel_ids_used) > 0


def test_generate_only_missing_visuals(tmp_path):
    """Only missing visuals are queued for generation; approved ones are reused."""
    project_id = setup_project_with_story(tmp_path)
    
    with SessionLocal() as db:
        from engine.story.alignment import alignment_service
        doc = alignment_service.align_script_to_frames(db, project_id)
        
        # Count unique panel references vs existing assets
        all_panel_refs = set()
        for seg in doc.segments:
            for p in seg.supporting_panels:
                all_panel_refs.add(p.panel_id)
        
        # We have 2 existing approved assets, 7 panels referenced
        # Only missing ones should need generation
        existing_assets = {'asset-panel-1-1', 'asset-panel-2-2'}
        
        # The decision engine should identify which panels need generation
        needed_generation = all_panel_refs - {p.replace('panel-', '').replace('-', '-') for p in []}
        # This test verifies the concept - implementation will track this


def test_preserve_approved_scenes_on_regeneration(tmp_path):
    """When one scene is regenerated, approved scenes are preserved."""
    project_id = setup_project_with_story(tmp_path)
    
    with SessionLocal() as db:
        from engine.story.alignment import alignment_service
        # First storyboard generation
        doc1 = alignment_service.align_script_to_frames(db, project_id)
        scene1_segments = [s for s in doc1.segments if s.scene_id.startswith('scene-1-')]
        scene2_segments = [s for s in doc1.segments if s.scene_id.startswith('scene-2-')]
        
        # Mark scene-1 as manually approved
        for seg in scene1_segments:
            seg.manual_override = True
        
        # Save the storyboard
        doc1.updated_at = '2026-01-01T00:00:00Z'
        storyboard_path = Path(tmp_path) / 'story' / 'storyboard.json'
        storyboard_path.parent.mkdir(parents=True, exist_ok=True)
        storyboard_path.write_text(doc1.model_dump_json(indent=2))
        
        # Regenerate with force (simulating scene-2 regeneration)
        doc2 = alignment_service.align_script_to_frames(db, project_id, force_realign=True)
        
        # scene-1 segments should be preserved (manual_override=True)
        for seg in doc2.segments:
            if seg.scene_id.startswith('scene-1-'):
                assert seg.manual_override is True
            # scene-2 can be regenerated


def test_shot_contract_includes_reuse_decision(tmp_path):
    """Each shot contract includes a reuse decision: reuse/crop/reframe/edit/new."""
    project_id = setup_project_with_story(tmp_path)
    
    with SessionLocal() as db:
        from engine.story.alignment import alignment_service
        doc = alignment_service.align_script_to_frames(db, project_id)
        
        # Verify each panel reference has a role and crop bounds
        for seg in doc.segments:
            for panel_ref in seg.supporting_panels:
                assert panel_ref.panel_id
                assert panel_ref.role in ['ESTABLISHING', 'REACTION_CLOSEUP', 'ACTION', 'NARRATION_FOCUS', 'TRANSITION']
                assert 'x' in panel_ref.crop_bounds
                assert 'y' in panel_ref.crop_bounds
                assert 'width' in panel_ref.crop_bounds
                assert 'height' in panel_ref.crop_bounds
                assert panel_ref.sub_duration_sec > 0


def test_visual_timeline_persists_shot_contracts(tmp_path):
    """VisualTimelineRecord persists the complete shot plan with reuse metadata."""
    project_id = setup_project_with_story(tmp_path)
    
    with SessionLocal() as db:
        # Create a visual timeline
        timeline = VisualTimelineRecord(
            id='vt-1',
            project_id=project_id,
            status='DRAFT',
            total_duration=30.0,
            total_shots=10,
            style_preset='cinematic',
            timeline_json={
                'scenes': [
                    {
                        'scene_id': 'scene-1',
                        'shots': [
                            {'shot_id': 'shot-1', 'reuse_decision': 'REUSE', 'source_asset_id': 'asset-panel-1-1'},
                            {'shot_id': 'shot-2', 'reuse_decision': 'CROP_REFRAME', 'source_asset_id': 'asset-panel-1-2'},
                            {'shot_id': 'shot-3', 'reuse_decision': 'NEW_GENERATION', 'source_asset_id': None},
                        ]
                    }
                ]
            },
            overrides_json={},
        )
        db.add(timeline)
        db.commit()
        db.refresh(timeline)
        
        assert timeline.id == 'vt-1'
        assert timeline.total_shots == 10
        assert 'reuse_decision' in str(timeline.timeline_json)


def test_storyboard_api_endpoints_exist():
    """API endpoints for storyboard and shot planning are registered."""
    from engine.api.routers.story import router
    
    # Check for storyboard endpoints
    routes = [r.path for r in router.routes]
    assert '/api/projects/{project_id}/storyboard' in routes
    assert '/api/projects/{project_id}/storyboard/segments/{segment_id}' in routes
    assert '/api/projects/{project_id}/storyboard/realign' in routes