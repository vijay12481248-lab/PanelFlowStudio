import sys
from pathlib import Path
sys.path.insert(0, ".")
from engine.original import explainer as ex
for f in sys.argv[1:]:
    try:
        s = ex.build_story(Path(f).read_text(encoding="utf-8"))
        w = sum(len(p.caption.split()) for p in s.panels)
        print(Path(f).name, len(s.panels), "beats", w, "words ~%ds" % ex.estimate_seconds(s), ex.lint(s))
    except ValueError as e:
        print(Path(f).name, "ERRORS:", str(e).replace("\n", " ; "))
