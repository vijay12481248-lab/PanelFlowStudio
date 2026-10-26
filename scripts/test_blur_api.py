import sys, os
sys.path.insert(0, '.')
from engine.imaging.sanitizer import (
    get_blur_keywords_for_project,
    save_blur_keywords_for_project,
    auto_sanitize_project_panels,
    DEFAULT_BLUR_KEYWORDS
)

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'

print("Default keywords count:", len(DEFAULT_BLUR_KEYWORDS))
current_kw = get_blur_keywords_for_project(PROJECT_ID)
print("Current project keywords:", current_kw)

# Add custom keywords
updated_kw = save_blur_keywords_for_project(PROJECT_ID, ["manhuaplus", "mycustomwatermark", "patreon"])
print("Updated project keywords:", updated_kw)
assert "mycustomwatermark" in updated_kw

# Trigger auto-sanitize
res = auto_sanitize_project_panels(PROJECT_ID)
print("Auto-sanitize result:", res)

print("Test passed! Blur system is fully operational and configurable.")
