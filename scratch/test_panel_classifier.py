import sys
sys.path.insert(0, ".")
import json
from pathlib import Path
from engine.imaging.panels.classification import PanelClassifier, PanelClassificationKind

panels_file = Path("output/manga_workflow_validation/panels.json")
with open(panels_file, "r", encoding="utf-8") as f:
    panels = json.load(f)

# Load existing observations if available
narrative_file = Path("output/manga_workflow_validation/story/narrative.json")
obs_map = {}
if narrative_file.exists():
    with open(narrative_file, "r", encoding="utf-8") as f:
        ndoc = json.load(f)
        obs_map = {o["panel_id"]: o["visual_summary"] for o in ndoc.get("observations", [])}

items = []
for p in panels:
    pid = p["panel_id"]
    order = p["reading_order"]
    src = p["source_image"]
    bbox = p["bbox"]
    vis_summary = obs_map.get(pid, "")
    
    # Check first / last page status
    is_first = (order == 1)
    is_last = (order == len(panels))
    
    item = PanelClassifier.classify_panel(
        panel_id=pid,
        reading_order=order,
        source_image=src,
        bbox=bbox,
        ocr_text="",
        vision_summary=vis_summary,
        is_first_on_first_page=is_first,
        is_last_on_last_page=is_last,
    )
    items.append(item)

report = PanelClassifier.generate_coverage_report("acceptance_demon_923", items)
print(f"Total Discovered: {report.total_discovered_panels}")
print(f"Story Panels: {report.total_story_panels}")
print(f"Non-Story Excluded: {report.total_non_story_panels}")
print(f"Uncertain: {report.total_uncertain_panels}")

print("\n--- Non-Story Excluded Panels ---")
for it in report.items:
    if it.classification != PanelClassificationKind.STORY_PANEL:
        print(f"  {it.panel_id} ({it.subtype.value}): {it.exclusion_reason}")

print("\n--- Story Panels Range ---")
story_ids = [it.panel_id for it in report.items if it.classification == PanelClassificationKind.STORY_PANEL]
print(f"  First Story Panel: {story_ids[0]}")
print(f"  Last Story Panel : {story_ids[-1]}")
print(f"  Count: {len(story_ids)}")
