"""Run make_reel stages for r16 without editing tools/reels/specs.py:  python tools/reels/run_lunch.py <stage> [r16]"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import specs  # noqa: E402
from spec_lunch import LUNCH  # noqa: E402

specs.REELS.append(LUNCH)
specs.NO_REF[LUNCH["slug"]] = {3, 5}  # scene 3 (the boss eats) and 5 (the crowd) must not inherit scene 1 composition
sys.argv = [str(HERE / "make_reel.py"), *sys.argv[1:]]
runpy.run_path(str(HERE / "make_reel.py"), run_name="__main__")
