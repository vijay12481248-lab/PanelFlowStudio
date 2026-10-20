with open('tests/unit/test_character_registry_reference.py', 'r') as f:
    content = f.read()

# Replace test_character_reference_asset_linking
old1 = '''def test_character_reference_asset_linking(tmp_path):
    """A character can have a canonical reference asset linked from AssetRecord."""
    setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        # Create character
        char = CharacterRecord(
            id='char-hero',
            project_id='char-ref-project',
            display_name='Hero',
            canonical_name='Hero Protagonist',
            visual_traits=['blue eyes', 'red cape'],
            role='PROTAGONIST',
            first_panel_id='panel-1',
            reference_panel_ids=['panel-1'],
            status='APPROVED',
            manual_override=True,
        )'''

new1 = '''def test_character_reference_asset_linking(tmp_path):
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
        )'''

# Replace test_character_generation_parameters_persisted
old2 = '''def test_character_generation_parameters_persisted(tmp_path):
    """Character stores the generation model/workflow/seed/provenance used for its reference."""
    setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        char = CharacterRecord(
            id='char-villain',
            project_id='char-ref-project',
            display_name='Villain',
            visual_traits=['green skin', 'horns'],
            role='ANTAGONIST',
            first_panel_id='panel-2',
            reference_panel_ids=['panel-2'],
            status='APPROVED',
            manual_override=True,
        )'''

new2 = '''def test_character_generation_parameters_persisted(tmp_path):
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
        )'''

# Replace test_character_approval_workflow
old3 = '''def test_character_approval_workflow(tmp_path):
    """Character changes require human approval; unapproved changes are staged."""
    setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        char = CharacterRecord(
            id='char-sidekick',
            project_id='char-ref-project',
            display_name='Sidekick',
            visual_traits=['yellow shirt'],
            role='SUPPORTING',
            first_panel_id='panel-1',
            reference_panel_ids=['panel-1'],
            status='DRAFT',
            manual_override=False,
        )'''

new3 = '''def test_character_approval_workflow(tmp_path):
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
        )'''

# Replace test_character_reference_selection_for_comfyui_job
old4 = '''def test_character_reference_selection_for_comfyui_job(tmp_path):
    """Character reference asset can be selected as input for ComfyUI consistent generation."""
    setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        char = CharacterRecord(
            id='char-consistent',
            project_id='char-ref-project',
            display_name='Consistent Hero',
            visual_traits=['silver armor'],
            role='PROTAGONIST',
            first_panel_id='panel-1',
            reference_panel_ids=['panel-1'],
            status='APPROVED',
            manual_override=True,
        )'''

new4 = '''def test_character_reference_selection_for_comfyui_job(tmp_path):
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
        )'''

# Replace test_two_characters_retain_traits_across_scenes
old5 = '''def test_two_characters_retain_traits_across_scenes(tmp_path):
    """Acceptance: two recurring characters keep approved traits across scenes."""
    setup_project_with_panels(tmp_path)
    with SessionLocal() as db:
        # Create two approved characters with distinct traits
        hero = CharacterRecord(
            id='char-hero-acceptance',
            project_id='char-ref-project',
            display_name='Hero',
            canonical_name='The Hero',
            visual_traits=['blue eyes', 'red cape', 'golden sword'],
            role='PROTAGONIST',
            first_panel_id='panel-1',
            reference_panel_ids=['panel-1', 'panel-2'],
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 111},
        )
        villain = CharacterRecord(
            id='char-villain-acceptance',
            project_id='char-ref-project',
            display_name='Villain',
            canonical_name='Dark Lord',
            visual_traits=['green skin', 'horns', 'black armor'],
            role='ANTAGONIST',
            first_panel_id='panel-2',
            reference_panel_ids=['panel-2'],
            status='APPROVED',
            manual_override=True,
            generation_params={'workflow_id': 'manga_image_generation', 'seed': 222},
        )'''

new5 = '''def test_two_characters_retain_traits_across_scenes(tmp_path):
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
        )'''

content = content.replace(old1, new1)
content = content.replace(old2, new2)
content = content.replace(old3, new3)
content = content.replace(old4, new4)
content = content.replace(old5, new5)

with open('tests/unit/test_character_registry_reference.py', 'w') as f:
    f.write(content)

print('SUCCESS: All test functions updated')