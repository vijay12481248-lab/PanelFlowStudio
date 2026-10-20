with open('tests/unit/test_motion_comic_slice.py', 'r') as f:
    content = f.read()

# Fix the setup function to use unique IDs per project
old_pages = """        # Pages and panels - use simple IDs that match visual timeline
        page_ids = []
        panel_ids_by_page = []
        for i in range(2):
            page_id = f'page-{i+1}'
            page_ids.append(page_id)
            db.add(PageRecord(
                id=page_id, project_id=project_id, sequence=i+1,
                filename=f'page{i+1}.jpg', status='READY', width=1920, height=1080,
                byte_size=1000, sha256='a' * 64,
            ))
            panel_ids = []
            for j in range(3):
                panel_id = f'panel-{i+1}-{j+1}'
                panel_ids.append(panel_id)
                db.add(PanelRecord(
                    id=panel_id, project_id=project_id, page_id=page_id,
                    sequence=j+1, page_sequence=j+1, x=0, y=0, width=640, height=360,
                    crop_filename=f'{panel_id}.jpg', status='CONFIRMED',
                ))
            panel_ids_by_page.append(panel_ids)"""

new_pages = """        # Pages and panels - use project-scoped unique IDs
        page_ids = []
        panel_ids_by_page = []
        for i in range(2):
            page_id = f'page-{project_id}-{i+1}'
            page_ids.append(page_id)
            db.add(PageRecord(
                id=page_id, project_id=project_id, sequence=i+1,
                filename=f'page{i+1}.jpg', status='READY', width=1920, height=1080,
                byte_size=1000, sha256='a' * 64,
            ))
            panel_ids = []
            for j in range(3):
                panel_id = f'panel-{project_id}-{i+1}-{j+1}'
                panel_ids.append(panel_id)
                db.add(PanelRecord(
                    id=panel_id, project_id=project_id, page_id=page_id,
                    sequence=j+1, page_sequence=j+1, x=0, y=0, width=640, height=360,
                    crop_filename=f'{panel_id}.jpg', status='CONFIRMED',
                ))
            panel_ids_by_page.append(panel_ids)"""

content = content.replace(old_pages, new_pages)

# Also update the panel file creation to match
old_panel_files = """        # Panel crops - create valid JPEG images
        panels_dir = tmp_path / "panels"
        panels_dir.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            for j in range(3):
                panel_id = f'panel-{i+1}-{j+1}'
                # Create a valid JPEG image
                img = Image.new('RGB', (640, 360), color=(i*100 + j*50, 100, 150))
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG')
                (panels_dir / f'panel-{i+1}-{j+1}.jpg').write_bytes(img_bytes.getvalue())"""

new_panel_files = """        # Panel crops - create valid JPEG images with project-scoped IDs
        panels_dir = tmp_path / "panels"
        panels_dir.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            for j in range(3):
                panel_id = f'panel-{project_id}-{i+1}-{j+1}'
                # Create a valid JPEG image
                img = Image.new('RGB', (640, 360), color=(i*100 + j*50, 100, 150))
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG')
                (panels_dir / f'{panel_id}.jpg').write_bytes(img_bytes.getvalue())"""

content = content.replace(old_panel_files, new_panel_files)

# Update the visual timeline to use project-scoped panel IDs - use simpler approach
# Replace the hardcoded panel IDs in the visual timeline
content = content.replace(
    '"source_asset_id": "panel-1-1"',
    '"source_asset_id": f"panel-{project_id}-1-1"'
)
content = content.replace(
    '"source_panel_id": "panel-1-1"',
    '"source_panel_id": f"panel-{project_id}-1-1"'
)
content = content.replace(
    '"source_asset_id": "panel-1-2"',
    '"source_asset_id": f"panel-{project_id}-1-2"'
)
content = content.replace(
    '"source_panel_id": "panel-1-2"',
    '"source_panel_id": f"panel-{project_id}-1-2"'
)
content = content.replace(
    '"source_asset_id": "panel-2-1"',
    '"source_asset_id": f"panel-{project_id}-2-1"'
)
content = content.replace(
    '"source_panel_id": "panel-2-1"',
    '"source_panel_id": f"panel-{project_id}-2-1"'
)
content = content.replace(
    '"source_asset_id": "panel-2-2"',
    '"source_asset_id": f"panel-{project_id}-2-2"'
)
content = content.replace(
    '"source_panel_id": "panel-2-2"',
    '"source_panel_id": f"panel-{project_id}-2-2"'
)

with open('tests/unit/test_motion_comic_slice.py', 'w') as f:
    f.write(content)

print('Fixed all IDs to be project-scoped')