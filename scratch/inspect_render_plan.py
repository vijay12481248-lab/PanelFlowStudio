import json
from pathlib import Path

plan_path = Path("output/acceptance_real_manga/work_0e194a4c/render_plan.json")
if not plan_path.exists():
    print("Plan not found")
    exit(1)

with open(plan_path, encoding="utf-8") as f:
    p = json.load(f)

shots = p["shots"]
print(f"Total shots: {len(shots)}")

for i, s in enumerate(shots):
    cap = s.get("captions", [{}])[0]
    words = len(cap.get("text", "").split())
    seg = cap.get("script_segment_id")
    asset = Path(s.get("source_asset_path", "")).name
    motion = s.get("motion_type")
    dur = s.get("duration", 0.0)
    print(f"Shot {i+1:02d}: dur={dur:.2f}s motion={motion} asset={asset} seg={seg} cap_words={words}")
