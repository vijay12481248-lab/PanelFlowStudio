"""Text embedders of the guide model: named, deterministic, remembered by the checkpoint, never silently swapped."""
from __future__ import annotations

from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file
from starlette.testclient import TestClient

from engine.api.app import app
from engine.motion_bank.guide import text_embed
from engine.motion_bank.guide.dataset import MotionBankDataset
from engine.motion_bank.guide.generator import MotionGenerator
from engine.motion_bank.guide.text_embed import TextEmbedderError, embed_one, embed_texts
from engine.motion_bank.guide.trainer import MotionGuideTrainer
from engine.motion_bank.models import MotionRecord
from engine.motion_bank.storage import MotionBankStorage

needs_clip = pytest.mark.skipif(
    not (text_embed.CLIP_WEIGHTS.is_file() and (text_embed.CLIP_TOKENIZER_DIR / "vocab.json").is_file()),
    reason="the CLIP-L text encoder that ComfyUI uses for HiDream is not on this machine",
)

GROUPS = {
    "kick": ["Spinning high kick", "Roundhouse kick to the head", "Martial artist lands a flying kick"],
    "sword": ["Samurai draws his sword and slashes", "Swordsman swings a blade overhead", "Knight cuts downward with a longsword"],
    "walk": ["Man walks slowly down a street", "Pedestrian strolls along the pavement", "Person walking with an umbrella"],
    "calm": ["Woman sits quietly reading a book", "Person rests in a chair and relaxes", "Girl sits still on a bench"],
}


def _nearest_in_group(embedder: str) -> int:
    names = [g for g, ts in GROUPS.items() for _ in ts]
    texts = [t for ts in GROUPS.values() for t in ts]
    emb = embed_texts(texts, embedder)
    sim = emb @ emb.T
    hits = 0
    for i in range(len(texts)):
        row = sim[i].clone()
        row[i] = -9
        hits += names[int(row.argmax())] == names[i]
    return hits


@needs_clip
def test_clip_embeddings_are_unit_length_deterministic_and_group_related_actions():
    a = embed_one("spinning kick", "clip")
    assert a.shape == (256,) and float(torch.norm(a)) == pytest.approx(1.0, abs=1e-4)
    assert torch.allclose(a, embed_one("spinning kick", "clip"), atol=1e-5)
    assert float(a @ embed_one("roundhouse kick", "clip")) > float(a @ embed_one("quiet reading", "clip"))
    # measured 2026-11-17: 12/12 with CLIP, 5/12 with the hash; the assertion leaves room, the point is the gap
    assert _nearest_in_group("clip") >= 10
    assert _nearest_in_group("clip") > _nearest_in_group("hash")


def test_missing_clip_files_are_an_error_not_a_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(text_embed, "CLIP_WEIGHTS", tmp_path / "nope.safetensors")
    with pytest.raises(TextEmbedderError):
        embed_texts(["x"], "clip")
    with pytest.raises(ValueError):
        embed_texts(["x"], "nope")


def _bank(tmp_path: Path, frames: int = 100) -> MotionBankStorage:
    storage = MotionBankStorage(tmp_path / "bank")
    for i, title in enumerate(["Spinning kick", "Quiet reading"]):
        kp = torch.rand(frames, 133, 3)
        save_file({"keypoints": kp}, str(tmp_path / f"m{i}.safetensors"))
        storage.save_motion(MotionRecord(
            id=f"m{i}", source_uri="x", action_title=title, duration_sec=1, fps=24, frame_count=frames, resolution=(10, 10),
            keypoints_path=str(tmp_path / f"m{i}.safetensors"), control_video_path=str(tmp_path / f"c{i}.mp4"),
        ))
    return storage


def test_dataset_takes_random_windows_of_long_motions(tmp_path: Path):
    ds = MotionBankDataset(_bank(tmp_path), target_seq_len=32, random_window=True)
    full = ds.storage.load_keypoints_tensor(Path(ds.records[0].keypoints_path))
    starts = set()
    for _ in range(40):
        window = ds[0]["pose_seq"]
        assert window.shape == (32, 133, 3)
        starts.add(int((full[:, 0, 0] == window[0, 0, 0]).nonzero()[0]))
    assert len(starts) > 1                              # not always the first 32 frames
    fixed = MotionBankDataset(_bank(tmp_path / "b"), target_seq_len=32)
    assert torch.equal(fixed[0]["pose_seq"], fixed.storage.load_keypoints_tensor(Path(fixed.records[0].keypoints_path))[:32])


@needs_clip
def test_checkpoint_remembers_its_embedder_and_generation_uses_it(tmp_path: Path, monkeypatch):
    trainer = MotionGuideTrainer(_bank(tmp_path), tmp_path / "ckpt", device="cpu")
    res = trainer.train(num_epochs=1, batch_size=2, embedder="clip")
    assert res["text_embedder"] == "clip" and res["motions"] == 2
    gen = MotionGenerator(checkpoint_path=Path(res["checkpoint"]), device="cpu")
    assert gen.embedder == "clip"
    calls = []
    real = text_embed.embed_texts
    monkeypatch.setattr("engine.motion_bank.guide.text_embed.embed_texts", lambda t, e="hash", d=256: (calls.append(e) or real(t, e, d)))
    assert len(gen.generate("a kick", num_frames=8, num_steps=3)) == 8
    assert calls == ["clip"]

    old = MotionGuideTrainer(_bank(tmp_path / "b"), tmp_path / "ckpt2", device="cpu")
    r2 = old.train(num_epochs=1, batch_size=2)           # the library default stays the offline hash
    assert r2["text_embedder"] == "hash"
    assert MotionGenerator(checkpoint_path=Path(r2["checkpoint"]), device="cpu").embedder == "hash"


def test_train_endpoint_reports_a_missing_embedder_as_503(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PANELFLOW_MOTION_BANK_DIR", str(tmp_path / "bank"))
    monkeypatch.setattr(text_embed, "CLIP_WEIGHTS", tmp_path / "nope.safetensors")
    from engine.api.routers import motion_bank as router

    kp = tmp_path / "k.safetensors"
    save_file({"keypoints": torch.rand(40, 133, 3)}, str(kp))
    router.get_storage().save_motion(MotionRecord(
        id="m", source_uri="x", action_title="t", duration_sec=1, fps=24, frame_count=40, resolution=(10, 10),
        keypoints_path=str(kp), control_video_path=str(tmp_path / "c.mp4")))
    res = TestClient(app).post("/api/motion_bank/guide/train", json={"num_epochs": 1})
    assert res.status_code == 503 and "clip" in res.json()["detail"]
