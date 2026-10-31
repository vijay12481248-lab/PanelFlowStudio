"""Fine-tune RT-DETRv2 (Apache-2.0) to detect panel / bubble / promo in 512x1024 strip tiles.

Usage: python scripts/panel_truth/train_detector.py <out_dir> <epochs> <dataset_dir> [<dataset_dir> ...]
A dataset dir holds images/ and labels.json from synth.py or real_tiles.py. Real dirs (name starts
with "real") are oversampled so they make up about a quarter of each epoch.
"""
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

BASE = "PekingU/rtdetr_v2_r18vd"
CLASSES = ["panel", "bubble", "promo"]
TW, TH = 512, 1024  # RT-DETR takes 0..1 RGB, no mean/std normalisation


class Tiles(Dataset):
    def __init__(self, dirs, train=True):
        self.items = []
        for d in dirs:
            d = Path(d)
            data = json.loads((d / "labels.json").read_text(encoding="utf-8"))
            for t in data["tiles"]:
                self.items.append((d / "images" / t["file"], t["labels"], d.name.startswith("real")))
        self.train = train

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, labels, _ = self.items[i]
        im = Image.open(path).convert("RGB")
        if im.size != (TW, TH):
            im = im.resize((TW, TH), Image.BILINEAR)
        if self.train:
            if random.random() < 0.8:
                im = ImageEnhance.Brightness(im).enhance(random.uniform(0.8, 1.2))
                im = ImageEnhance.Contrast(im).enhance(random.uniform(0.8, 1.2))
                im = ImageEnhance.Color(im).enhance(random.uniform(0.7, 1.3))
        x = torch.from_numpy(np.asarray(im, dtype=np.float32) / 255.0).permute(2, 0, 1)
        boxes, cls = [], []
        for lab in labels:
            x0, y0, x1, y1 = lab["box"]
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            boxes.append([(x0 + x1) / 2 / TW, (y0 + y1) / 2 / TH, (x1 - x0) / TW, (y1 - y0) / TH])
            cls.append(CLASSES.index(lab["class"]))
        target = {"class_labels": torch.tensor(cls, dtype=torch.long),
                  "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4)}
        return x, target


def collate(batch):
    return torch.stack([b[0] for b in batch]), [b[1] for b in batch]


def main(out_dir, epochs, dirs, batch=8, lr=1e-4):
    from transformers import RTDetrV2ForObjectDetection
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = Tiles(dirs)
    real = np.array([r for _, _, r in data.items])
    weights = np.where(real, 0.25 / max(1, real.sum()), 0.75 / max(1, (~real).sum()))
    sampler = WeightedRandomSampler(weights.tolist(), num_samples=len(data), replacement=True)
    loader = DataLoader(data, batch_size=batch, sampler=sampler, collate_fn=collate, num_workers=4,
                        persistent_workers=True)
    model = RTDetrV2ForObjectDetection.from_pretrained(
        BASE, num_labels=len(CLASSES), id2label=dict(enumerate(CLASSES)),
        label2id={c: i for i, c in enumerate(CLASSES)}, ignore_mismatched_sizes=True).cuda()
    backbone = [p for n, p in model.named_parameters() if "backbone" in n]
    rest = [p for n, p in model.named_parameters() if "backbone" not in n]
    opt = torch.optim.AdamW([{"params": backbone, "lr": lr * 0.1}, {"params": rest, "lr": lr}], weight_decay=1e-4)
    steps = epochs * len(loader)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / 300) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps))))
    scaler = torch.amp.GradScaler("cuda")
    step, t0 = 0, time.time()
    model.train()
    for epoch in range(epochs):
        running = 0.0
        for x, targets in loader:
            x = x.cuda(non_blocking=True)
            targets = [{k: v.cuda() for k, v in t.items()} for t in targets]
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(pixel_values=x, labels=targets).loss
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)
            scaler.step(opt)
            scaler.update()
            sched.step()
            running += loss.item()
            step += 1
            if step % 100 == 0:
                print(f"epoch {epoch} step {step}/{steps} loss {running / 100:.3f} {time.time() - t0:.0f}s", flush=True)
                running = 0.0
        model.save_pretrained(out)
    (out / "classes.json").write_text(json.dumps(CLASSES))
    print("saved", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], int(a[1]), a[2:])
