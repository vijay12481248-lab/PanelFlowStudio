"""Score line readers on the hand-transcribed eval lines: character error rate and exact-line rate.

Usage: python scripts/ocr_train/evaluate_ocr.py <eval_dir> [windows|trocr:<model_dir>] ...
"""
import json
import re
import sys
from pathlib import Path


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s.upper()).strip()


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(pred: dict[str, str], truth: dict[str, str]) -> dict:
    errs = sum(edit_distance(norm(pred.get(k, "")), norm(t)) for k, t in truth.items())
    chars = sum(len(norm(t)) for t in truth.values())
    exact = sum(norm(pred.get(k, "")) == norm(t) for k, t in truth.items())
    return {"lines": len(truth), "cer": round(errs / chars, 4), "exact_lines": f"{exact}/{len(truth)}"}


def read_all(engine: str, eval_dir: Path, truth: dict[str, str]) -> dict[str, str]:
    cands = json.loads((eval_dir / "candidates.json").read_text(encoding="utf-8"))
    if engine == "windows":  # the text the pipeline actually used for this line
        return {k: cands[int(k)]["windows_text"] for k in truth}
    if engine.startswith("trocr:"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from engine.training.line_reader import LineReader
        reader = LineReader(Path(engine[6:]))
        from PIL import Image
        return {k: reader.read(Image.open(eval_dir / "lines" / cands[int(k)]["file"]).convert("RGB")) for k in truth}
    raise SystemExit(f"unknown engine {engine}")


if __name__ == "__main__":
    eval_dir = Path(sys.argv[1])
    truth = json.loads((eval_dir / "truth.json").read_text(encoding="utf-8"))["lines"]
    for engine in sys.argv[2:] or ["windows"]:
        pred = read_all(engine, eval_dir, truth)
        print(f"{engine:40} {score(pred, truth)}")
        if "-v" in sys.argv:
            for k, t in truth.items():
                if norm(pred.get(k, "")) != norm(t):
                    print(f"   #{k}: truth={t!r} got={pred.get(k)!r}")
