import sys
from pathlib import Path
sys.path.insert(0, ".")
from engine.original import explainer as ex
for f in sys.argv[1:]:
    try:
        s = ex.build_story(Path(f).read_text(encoding="utf-8"))
        print(Path(f).name, len(s.panels), "beats ~%ds" % ex.estimate_seconds(s), [w for w in ex.lint(s) if "diagram beats" not in w])
    except ValueError as e:
        print(Path(f).name, "ERRORS:\n", e)
