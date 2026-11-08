"""Print `pid  chars | narration` of a full explainer spec, to pick the beats a Short reuses: python stories/index_beats.py 01_yawn.txt [...]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.original import explainer as ex  # noqa: E402

for name in sys.argv[1:]:
    s = ex.build_story((ex.EXPLAINER_DIR / name).read_text(encoding="utf-8"))
    print(f"## {name}")
    for p in s.panels:
        print(f"{p.id} [{','.join(p.character_ids) or '-'}] {p.caption}")
