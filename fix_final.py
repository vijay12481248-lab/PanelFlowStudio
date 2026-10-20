import re

with open('tests/unit/test_storyboard_asset_reuse.py', 'r') as f:
    content = f.read()

# Find the setup function and replace it entirely
new_setup = '''def setup_project_with_story(tmp_path):
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
        script = VideoScriptRecord(
            id='script-1',
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
                id=seg_id, script_id='script-1', project_id=project_id,
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
    return project_id'''

# Read the file
with open('tests/unit/test_storyboard_asset_reuse.py', 'r') as f:
    content = f.read()

# Find the setup function and replace it entirely
pattern = r'def setup_project_with_story\(tmp_path\):.*?return project_id\n'
replacement = 'def setup_project_with_story(tmp_path):\n    """Create a test project with script, scenes, and panels."""\n' + \
    """    project_id = f'storyboard-test-{uuid.uuid4().hex[:8]}'\n    Base.metadata.create_all(bind=engine)\n    run_sqlite_migrations(engine)\n    with SessionLocal() as db:\n        db.add(ProjectRecord(\n            id=project_id,\n            title='Storyboard Test',\n            source_type='LOCAL_FOLDER',\n            rights_status='PUBLIC_DOMAIN',\n            workspace_path=str(tmp_path),\n            current_stage=PipelineStage.STORY_APPROVED.value,\n        ))\n        # Pages and panels - use unique IDs per test run\n        page_ids = []\n        panel_ids_by_page = []\n        for i in range(3):\n            page_id = f'page-{i+1}-{uuid.uuid4().hex[:8]}'\n            page_ids.append(page_id)\n            db.add(PageRecord(\n                id=page_id, project_id=project_id, sequence=i+1,\n                filename=f'page{i+1}.jpg', status='READY', width=1024, height=1536,\n                byte_size=1000, sha256='a' * 64,\n            ))\n            panel_ids = []\n            for j in range(3):\n                panel_id = f'panel-{i+1}-{j+1}-{uuid.uuid4().hex[:8]}'\n                panel_ids.append(panel_id)\n                db.add(PanelRecord(\n                    id=panel_id, project_id=project_id, page_id=page_id,\n                    sequence=j+1, page_sequence=j+1, x=0, y=0, width=512, height=768,\n                    crop_filename=f'{panel_id}.jpg', status='CONFIRMED',\n                ))\n            panel_ids_by_page.append(panel_ids)\n\n        # Scenes - use unique IDs per test run\n        scene1_id = f'scene-1-{uuid.uuid4().hex[:8]}'\n        scene2_id = f'scene-2-{uuid.uuid4().hex[:8]}'\n        # Use first panel of first page as scene-1 start, last panel of first page as scene-1 end\n        # Use first panel of second page as scene-2 start, last panel of third page as scene-2 end\n        scene1_start = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]\n        scene1_end = panel_ids_by_page[0][-1] if panel_ids_by_page[0] else page_ids[0]\n        scene2_start = panel_ids_by_page[1][0] if len(panel_ids_by_page) > 1 and panel_ids_by_page[1] else page_ids[1]\n        scene2_end = panel_ids_by_page[-1][-1] if panel_ids_by_page[-1] else page_ids[-1]\n\n        db.add(SceneRecord(\n            id=scene1_id, project_id=project_id, sequence=1,\n            title='The Ruins', panel_start=scene1_start, panel_end=scene1_end,\n            character_ids=[], summary='Hero explores ruins.',\n        ))\n        db.add(SceneRecord(\n            id=scene2_id, project_id=project_id, sequence=2,\n            title='The Guardian', panel_start=scene2_start, panel_end=scene2_end,\n            character_ids=[], summary='Guardian battle.',\n        ))\n\n        # Approved script\n        script = VideoScriptRecord(\n            id='script-1',\n            project_id=project_id,\n            version='1.0',\n            adaptation_profile='FAITHFUL',\n            estimated_duration=30.0,\n            language='en',\n            status='APPROVED',\n            quality_metrics={},\n        )\n        db.add(script)\n        # 5 segments across 2 scenes - use the dynamic scene IDs\n        segments = [\n            (f'seg-1-{uuid.uuid4().hex[:8]}', scene1_id, 1, 'CHARACTER_DIALOGUE', 'Hero enters the ruins.', 'NEUTRAL', 0.5, 3.0),\n            (f'seg-2-{uuid.uuid4().hex[:8]}', scene1_id, 2, 'NARRATION', 'The ancient stones glow.', 'MYSTERIOUS', 0.6, 4.0),\n            (f'seg-3-{uuid.uuid4().hex[:8]}', scene1_id, 3, 'CHARACTER_DIALOGUE', 'I sense danger ahead.', 'TENSE', 0.8, 3.5),\n            (f'seg-4-{uuid.uuid4().hex[:8]}', scene2_id, 1, 'NARRATION', 'A guardian awakens.', 'DRAMATIC', 0.7, 4.5),\n            (f'seg-5-{uuid.uuid4().hex[:8]}', scene2_id, 2, 'CHARACTER_DIALOGUE', 'We must fight!', 'EXCITED', 0.9, 3.0),\n        ]\n        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:\n            db.add(ScriptSegmentRecord(\n                id=seg_id, script_id='script-1', project_id=project_id,\n                scene_id=scene_id, sequence=seq, type=seg_type,\n                speaker_character_id=None, text=text, emotion=emotion,\n                intensity=intensity, estimated_duration=dur,\n                estimated_start=0.0, estimated_end=dur,\n                source_evidence={}, production_intent='',\n            ))\n\n        # Characters with reference assets - use unique IDs per test run\n        hero_id = f'char-hero-{uuid.uuid4().hex[:8]}'\n        villain_id = f'char-villain-{uuid.uuid4().hex[:8]}'\n        # Use dynamic panel IDs for character references\n        hero_first_panel = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]\n        hero_ref_panels = panel_ids_by_page[0][:2] if len(panel_ids_by_page[0]) >= 2 else [panel_ids_by_page[0][0]]\n        villain_first_panel = panel_ids_by_page[2][0] if len(panel_ids_by_page) > 2 and panel_ids_by_page[2] else page_ids[-1]\n        villain_ref_panels = panel_ids_by_page[2][:1] if len(panel_ids_by_page) > 2 and panel_ids_by_page[2] else [panel_ids_by_page[-1][0]]\n\n        hero = CharacterRecord(\n            id=f'char-hero-{uuid.uuid4().hex[:8]}',\n            project_id=project_id,\n            display_name='Hero',\n            visual_traits=['blue armor', 'sword'],\n            role='PROTAGONIST',\n            first_panel_id=hero_first_panel,\n            reference_panel_ids=hero_ref_panels,\n            status='APPROVED',\n            manual_override=True,\n            generation_params={'workflow_id': 'manga_image_generation', 'seed': 111},\n        )\n        villain = CharacterRecord(\n            id=f'char-villain-{uuid.uuid4().hex[:8]}',\n            project_id=project_id,\n            display_name='Guardian',\n            visual_traits=['stone body', 'glowing eyes'],\n            role='ANTAGONIST',\n            first_panel_id=villain_first_panel,\n            reference_panel_ids=villain_ref_panels,\n            status='APPROVED',\n            manual_override=True,\n            generation_params={'workflow_id': 'manga_image_generation', 'seed': 222},\n        )\n        db.add_all([hero, villain])\n\n        # Existing approved visual assets (reusable) - use unique IDs per test run\n        asset1_id = f'asset-panel-1-1-{uuid.uuid4().hex[:8]}'\n        asset2_id = f'asset-panel-2-2-{uuid.uuid4().hex[:8]}'\n        # Use dynamic panel IDs for asset references\n        asset1_panel = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]\n        asset2_panel = panel_ids_by_page[1][1] if len(panel_ids_by_page) > 1 and len(panel_ids_by_page[1]) > 1 else page_ids[1]\n\n        db.add(AssetRecord(\n            id=asset1_id,\n            project_id=project_id,\n            asset_type='PANEL_CROP',\n            filename=f'{asset1_panel}.jpg',\n            relative_path=f'panels/{asset1_panel}.jpg',\n            content_type='image/jpeg',\n            width=512, height=768, byte_size=50000, sha256='b' * 64,\n            provenance={'workflow_id': 'manga_image_generation', 'seed': 111},\n            status='READY',\n        ))\n        db.add(AssetRecord(\n            id=asset2_id,\n            project_id=project_id,\n            asset_type='PANEL_CROP',\n            filename=f'{asset2_panel}.jpg',\n            relative_path=f'panels/{asset2_panel}.jpg',\n            content_type='image/jpeg',\n            width=512, height=768, byte_size=50000, sha256='c' * 64,\n            provenance={'workflow_id': 'manga_image_generation', 'seed': 333},\n            status='READY',\n        ))\n\n        db.commit()\n    return project_id\n"""

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('tests/unit/test_storyboard_asset_reuse.py', 'w') as f:
    f.write(content)

print('Setup function replaced')