"""
CLI tool for inspecting and generating preview keyframes from a VisualTimeline JSON file.

Usage:
    python tools/motion/preview_timeline.py <timeline_json_path> [--render-out <dir>]
"""
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.motion.models.timeline import VisualTimeline
from engine.motion.preview import MotionPreviewGenerator


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    timeline_path = Path(sys.argv[1])
    if not timeline_path.exists():
        print(f"Error: Timeline file '{timeline_path}' not found.")
        sys.exit(1)

    with open(timeline_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    timeline = VisualTimeline.model_validate(data)
    print(timeline.to_debug_string())

    if "--render-out" in sys.argv:
        out_idx = sys.argv.index("--render-out") + 1
        if out_idx < len(sys.argv):
            out_dir = Path(sys.argv[out_idx])
            preview_gen = MotionPreviewGenerator()
            rendered = preview_gen.export_timeline_keyframes(timeline, {}, out_dir)
            print(f"\nRendered {len(rendered)} preview keyframes to {out_dir}")


if __name__ == "__main__":
    main()
