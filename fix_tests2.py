with open('tests/unit/test_character_registry_reference.py', 'r') as f:
    content = f.read()

# Fix test_character_reference_asset_linking - use project_id instead of hardcoded
old1 = '''            # Create reference asset (generated image)
            asset = AssetRecord(
                id='asset-hero-ref',
                project_id='char-ref-project',
                asset_type='CHARACTER_REFERENCE',
                filename='hero_ref.png',
                relative_path='references/hero_ref.png',
                content_type='image/png',
                width=512,
                height=768,
                byte_size=50000,
                sha256='b' * 64,
                provenance={'workflow_id': 'manga_consistent_qwen_image_edit', 'seed': 42, 'model': 'qwen'},
            )'''

new1 = '''            # Create reference asset (generated image)
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
            )'''

# Fix test_character_reference_selection_for_comfyui_job
old2 = '''            # Reference asset
            asset = AssetRecord(
                id='asset-consistent-ref',
                project_id='char-ref-project',
                asset_type='CHARACTER_REFERENCE',
                filename='consistent_ref.png',
                relative_path='references/consistent_ref.png',
                content_type='image/png',
                width=512,
                height=768,
                byte_size=60000,
                sha256='c' * 64,
                provenance={'workflow_id': 'manga_consistent_qwen_image_edit', 'seed': 999},
            )'''

new2 = '''            # Reference asset
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
            )'''

# Fix test_two_characters_retain_traits_across_scenes
old3 = '''            # Verify traits are stable and retrievable
            chars = story_service.list_characters(db, 'char-ref-project')'''

new3 = '''            # Verify traits are stable and retrievable
            chars = story_service.list_characters(db, project_id)'''

content = content.replace(old1, new1)
content = content.replace(old2, new2)
content = content.replace(old3, new3)

with open('tests/unit/test_character_registry_reference.py', 'w') as f:
    f.write(content)

print('SUCCESS: Test project_id references fixed')