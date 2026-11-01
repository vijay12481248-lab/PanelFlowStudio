"""Fine-tune TrOCR-small (MIT) on synthetic comic lettering, score it on real hand-checked lines, publish it.

Usage: python scripts/ocr_train/train_trocr.py <run_dir> <eval_dir> [--steps N] [--batch N] [--publish]
Every checkpoint is kept (step_N); nothing is overwritten or deleted.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from engine.training.line_reader import LineReader, preprocess  # noqa: E402
from evaluate_ocr import edit_distance, norm, score  # noqa: E402
from synth_lines import LineSynth, load_corpus  # noqa: E402

BASE = "microsoft/trocr-small-printed"
MAX_LEN = 48


def batches(n_batches: int, batch: int, offset: int, seed: int = 1, threads: int = 6, ahead: int = 3):
    """Synthetic batches rendered by threads in this process.

    Worker processes each reserved 2.5 GB of Windows commit just to import torch, which together with the
    trainer used up the machine's whole commit limit and killed the run. PIL releases the GIL, so threads keep up.
    A resumed run passes `offset` so it continues with samples it has not seen."""
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    synth = LineSynth(seed=seed)

    def one(i):
        img, text = synth.render(i)
        return preprocess(img), text

    with ThreadPoolExecutor(threads) as pool:
        def submit(b):
            return [pool.submit(one, offset + b * batch + k) for k in range(batch)]
        pending = deque(submit(b) for b in range(min(ahead, n_batches)))
        for b in range(n_batches):
            futs = pending.popleft()
            if b + ahead < n_batches:
                pending.append(submit(b + ahead))
            rows = [f.result() for f in futs]
            yield torch.from_numpy(np.stack([r[0] for r in rows])), [r[1] for r in rows]


def synthetic_cer(reader: LineReader, n: int = 300) -> float:
    synth, imgs, texts = LineSynth(seed=99991), [], []
    for i in range(n):
        im, t = synth.render(i)
        imgs.append(im)
        texts.append(t)
    preds = [p for s in range(0, n, 50) for p in reader.read_batch(imgs[s:s + 50], beams=1)]
    return sum(edit_distance(norm(p), norm(t)) for p, t in zip(preds, texts)) / sum(len(norm(t)) for t in texts)


def real_score(reader: LineReader, eval_dir: Path, beams: int = 1) -> dict:
    truth = json.loads((eval_dir / "truth.json").read_text(encoding="utf-8"))["lines"]
    cands = json.loads((eval_dir / "candidates.json").read_text(encoding="utf-8"))
    imgs = [Image.open(eval_dir / "lines" / cands[int(k)]["file"]).convert("RGB") for k in truth]
    preds = reader.read_batch(imgs, beams=beams)
    return score(dict(zip(truth, preds)), truth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("eval_dir")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--eval_every", type=int, default=1000)
    ap.add_argument("--save_every", type=int, default=500)
    ap.add_argument("--workers", type=int, default=6, help="rendering threads")
    ap.add_argument("--resume", action="store_true", help="continue from the newest step_N checkpoint in run_dir")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    from transformers import AutoTokenizer, VisionEncoderDecoderModel

    run, eval_dir = Path(args.run_dir), Path(args.eval_dir)
    run.mkdir(parents=True, exist_ok=True)
    done = max((int(p.name[5:]) for p in run.glob("step_*") if p.name[5:].isdigit()), default=0) if args.resume else 0
    tokenizer = AutoTokenizer.from_pretrained(BASE)
    model = VisionEncoderDecoderModel.from_pretrained(str(run / f"step_{done}") if done else BASE).cuda()
    start = model.config.decoder.decoder_start_token_id
    model.config.pad_token_id = model.generation_config.pad_token_id = tokenizer.pad_token_id
    model.config.decoder_start_token_id = model.generation_config.decoder_start_token_id = start
    model.config.vocab_size = model.config.decoder.vocab_size
    model.generation_config.eos_token_id = tokenizer.sep_token_id if tokenizer.sep_token_id is not None else tokenizer.eos_token_id
    loader = batches(args.steps - done, args.batch, done * args.batch, threads=args.workers)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    warm = 50 if done else 200  # a resumed run has lost its optimizer moments, so ease back in
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, (s + done) / args.steps))))
    hist_path = run / "history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if done and hist_path.exists() else []
    t0, running = time.time(), 0.0
    model.train()
    for step, (x, texts) in enumerate(loader, start=done + 1):
        labels = tokenizer(texts, padding="max_length", max_length=MAX_LEN, truncation=True, return_tensors="pt").input_ids
        labels[labels == tokenizer.pad_token_id] = -100
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = model(pixel_values=x.cuda(non_blocking=True), labels=labels.cuda()).loss
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        running += loss.item()
        if step % 100 == 0:
            print(f"step {step}/{args.steps} loss {running / 100:.3f} {time.time() - t0:.0f}s", flush=True)
            running = 0.0
        if step % args.save_every == 0 and step % args.eval_every:
            ckpt = run / f"step_{step}"
            model.save_pretrained(ckpt)
            tokenizer.save_pretrained(ckpt)
        if step % args.eval_every == 0 or step == args.steps:
            ckpt = run / f"step_{step}"
            model.save_pretrained(ckpt)
            tokenizer.save_pretrained(ckpt)
            model.eval()
            reader = LineReader(model=model, tokenizer=tokenizer)
            row = {"step": step, "synthetic_cer": round(synthetic_cer(reader), 4), "real": real_score(reader, eval_dir)}
            history.append(row)
            print("EVAL", json.dumps(row), flush=True)
            (run / "history.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
            model.train()
    final = run / f"step_{args.steps}"
    if args.publish:
        from engine.training.registry import ModelStore
        reader = LineReader(final)
        best = real_score(reader, eval_dir, beams=4)
        v = ModelStore().publish(
            "comic_line_reader", final, base_model=f"{BASE} (MIT)",
            metrics={"real_cer_beam4": best["cer"], "real_exact_lines": best["exact_lines"], "synthetic_cer": history[-1]["synthetic_cer"]},
            data={"steps": args.steps, "batch": args.batch, "lr": args.lr, "synthetic_seed": 1,
                  "real_eval": "36 hand-transcribed Ch 928 lines, never trained on", "baseline_windows_ocr_cer": 0.1171,
                  "recipe": "scripts/ocr_train/{synth_lines,train_trocr}.py"})
        print("PUBLISHED comic_line_reader v", v, best)


if __name__ == "__main__":
    main()
