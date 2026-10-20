with open('tests/unit/test_storyboard_asset_reuse.py', 'r') as f:
    content = f.read()

# Fix page and panel IDs to be unique per test run
old_pages = '''        # Pages and panels
        for i in range(3):
            page_id = f'page-{i+1}'
            db.add(PageRecord(
                id=page_id, project_id=project_id, sequence=i+1,
                filename=f'page{i+1}.jpg', status='READY', width=1024, height=1536,
                byte_size=1000, sha256='a' * 64,
            ))
            for j in range(3):
                panel_id = f'panel-{i+1}-{j+1}'
                db.add(PanelRecord(
                    id=panel_id, project_id=project_id, page_id=page_id,
                    sequence=j+1, page_sequence=j+1, x=0, y=0, width=512, height=768,
                    crop_filename=f'{panel_id}.jpg', status='CONFIRMED',
                ))'''

new_pages = """        # Pages and panels - use unique IDs per test run
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
            panel_ids_by_page.append(panel_ids)"""

content = content.replace(old_pages, new_pages)

# Also need to update the script segments to use the correct scene IDs and panel references
# The scene IDs are also hardcoded - need to fix those too
old_scenes = """        # Scenes
        db.add(SceneRecord(
            id='scene-1', project_id=project_id, sequence=1,
            title='The Ruins', panel_start='panel-1-1', panel_end='panel-1-3',
            character_ids=[], summary='Hero explores ruins.',
        ))
        db.add(SceneRecord(
            id='scene-2', project_id=project_id, sequence=2,
            title='The Guardian', panel_start='panel-2-1', panel_end='panel-3-3',
            character_ids=[], summary='Guardian battle.',
        ))"""

new_scenes = """        # Scenes - use unique IDs per test run
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
        ))"""

content = content.replace(old_scenes, new_scenes)

# Also need to update the script segments to use the correct scene IDs
old_segments = """        # 5 segments across 2 scenes
        segments = [
            ('seg-1', 'scene-1', 1, 'CHARACTER_DIALOGUE', 'Hero enters the ruins.', 'NEUTRAL', 0.5, 3.0),
            ('seg-2', 'scene-1', 2, 'NARRATION', 'The ancient stones glow.', 'MYSTERIOUS', 0.6, 4.0),
            ('seg-3', 'scene-1', 3, 'CHARACTER_DIALOGUE', 'I sense danger ahead.', 'TENSE', 0.8, 3.5),
            ('seg-4', 'scene-2', 1, 'NARRATION', 'A guardian awakens.', 'DRAMATIC', 0.7, 4.5),
            ('seg-5', 'scene-2', 2, 'CHARACTER_DIALOGUE', 'We must fight!', 'EXCITED', 0.9, 3.0),
        ]
        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:"""

new_segments = """        # 5 segments across 2 scenes - use the dynamic scene IDs
        segments = [
            (f'seg-1-{uuid.uuid4().hex[:8]}', scene1_id, 1, 'CHARACTER_DIALOGUE', 'Hero enters the ruins.', 'NEUTRAL', 0.5, 3.0),
            (f'seg-2-{uuid.uuid4().hex[:8]}', scene1_id, 2, 'NARRATION', 'The ancient stones glow.', 'MYSTERIOUS', 0.6, 4.0),
            (f'seg-3-{uuid.uuid4().hex[:8]}', scene1_id, 3, 'CHARACTER_DIALOGUE', 'I sense danger ahead.', 'TENSE', 0.8, 3.5),
            (f'seg-4-{uuid.uuid4().hex[:8]}', scene2_id, 1, 'NARRATION', 'A guardian awakens.', 'DRAMATIC', 0.7, 4.5),
            (f'seg-5-{uuid.uuid4().hex[:8]}', scene2_id, 2, 'CHARACTER_DIALOGUE', 'We must fight!', 'EXCITED', 0.9, 3.0),
        ]
        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:"""

content = content.replace(old_segments, new_segments)

# Also need to update character panel references to use the dynamic panel IDs
old_char_refs = """        hero = CharacterRecord(
            id=hero_id,
            project_id=project_id,
            display_name='Hero',
            visual_traits=['blue armor', 'sword'],
            role='PROTAGONIST',
            first_panel_id='panel-1-1',
            reference_panel_ids=['panel-1-1', 'panel-1-2'],
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 111},
        )
        villain = CharacterRecord(
            id=villain_id,
            project_id=project_id,
            display_name='Guardian',
            visual_traits=['stone body', 'glowing eyes'],
            role='ANTAGONIST',
            first_panel_id='panel-3-1',
            reference_panel_ids=['panel-3-1'],
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 222},
        )"""

new_char_refs = """        # Use dynamic panel IDs for character references
        hero_first_panel = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]
        hero_ref_panels = panel_ids_by_page[0][:2] if len(panel_ids_by_page[0]) >= 2 else [panel_ids_by_page[0][0]]
        villain_first_panel = panel_ids_by_page[2][0] if len(panel_ids_by_page) > 2 and panel_ids_by_page[2] else page_ids[-1]
        villain_ref_panels = panel_ids_by_page[2][:1] if len(panel_ids_by_page) > 2 and panel_ids_by_page[2] else [panel_ids_by_page[-1][0]]
        
        hero = CharacterRecord(
            id=hero_id,
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
            id=villain_id,
            project_id=project_id,
            display_name='Guardian',
            visual_traits=['stone body', 'glowing eyes'],
            role='ANTAGONIST',
            first_panel_id=villain_first_panel,
            reference_panel_ids=villain_ref_panels,
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 222},
        )"""

content = content.replace(old_char_refs, new_char_refs)

# Also need to update asset panel references
old_asset_refs = """        db.add(AssetRecord(
            id=asset1_id,
            project_id=project_id,
            asset_type='PANEL_CROP',
            filename='panel-1-1.jpg',
            relative_path='panels/panel-1-1.jpg',
            content_type='image/jpeg',
            width=512, height=768, byte_size=50000, sha256='b' * 64,
            provenance={'workflow_id': 'manga_image_generation', 'seed': 111},
            status='READY',
        ))
        db.add(AssetRecord(
            id=asset2_id,
            project_id=project_id,
            asset_type='PANEL_CROP',
            filename='panel-2-2.jpg',
            relative_path='panels/panel-2-2.jpg',
            content_type='image/jpeg',
            width=512, height=768, byte_size=50000, sha256='c' * 64,
            provenance={'workflow_id': 'manga_image_generation', 'seed': 333},
            status='READY',
        ))"""

new_asset_refs = """        # Use dynamic panel IDs for asset references
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
        ))"""

content = content.replace(old_asset_refs, new_asset_refs)

with open('tests/unit/test_storyboard_asset_reuse.py', 'w') as f:
    f.write(content)

print('Fixed all IDs to be unique per test run')