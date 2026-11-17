"""Unit tests for Motion Guide subsystem (Motion-DiT, Dataset, Trainer, Generator)."""
from __future__ import annotations

from pathlib import Path
import pytest
import torch

from engine.motion_bank.guide.dataset import MotionBankDataset, embed_text_deterministic
from engine.motion_bank.guide.generator import MotionGenerator
from engine.motion_bank.guide.motion_dit import MotionChoreographerDiT
from engine.motion_bank.guide.trainer import MotionGuideTrainer
from engine.motion_bank.models import MotionRecord
from engine.motion_bank.storage import MotionBankStorage


def test_text_embedding_deterministic():
    """Verifies that deterministic text embedding produces fixed-size normalized vectors."""
    t1 = embed_text_deterministic("Samurai sword slash")
    t2 = embed_text_deterministic("Samurai sword slash")
    t3 = embed_text_deterministic("Girl walking in rain")

    assert t1.shape == (256,)
    assert torch.allclose(t1, t2)
    assert not torch.allclose(t1, t3)
    norm = float(torch.norm(t1))
    assert 0.99 <= norm <= 1.01


def test_motion_dit_forward_pass():
    """Verifies DiT forward pass produces correct noise prediction shape (B, T, 133, 3)."""
    model = MotionChoreographerDiT(num_keypoints=133, coords_per_kp=3, hidden_dim=64, depth=2, num_heads=2)
    B, T = 2, 16
    x_t = torch.randn((B, T, 133, 3))
    timesteps = torch.tensor([50, 100])
    text_embed = torch.randn((B, 256))

    out = model(x_t, timesteps, text_embed)
    assert out.shape == (B, T, 133, 3)


def test_guide_trainer_and_generator_flow(tmp_path: Path):
    """Verifies end-to-end training and generation flow."""
    storage = MotionBankStorage(tmp_path / "storage")

    # Seed 2 motion records
    for i in range(2):
        kp_path = tmp_path / f"motion_{i}.safetensors"
        # Create dummy kinematics [32, 133, 3]
        kinematics = torch.full((32, 133, 3), 0.5 + i * 0.1, dtype=torch.float32)
        from safetensors.torch import save_file
        save_file({"keypoints": kinematics}, str(kp_path))

        rec = MotionRecord(
            id=f"mot_test_{i}",
            source_uri=f"test://action_{i}",
            action_title=f"Action Move {i}",
            action_tags=["fight", "martial_arts"],
            duration_sec=1.33,
            fps=24.0,
            frame_count=32,
            resolution=(640, 360),
            keypoints_path=str(kp_path),
            control_video_path=str(tmp_path / f"control_{i}.mp4"),
        )
        storage.save_motion(rec)

    # 1. Train Guide model for 2 epochs
    trainer = MotionGuideTrainer(
        storage=storage,
        output_dir=tmp_path / "checkpoints",
        device="cpu",  # run test on CPU for quick CI execution
    )
    res = trainer.train(num_epochs=2, batch_size=2)
    assert res["status"] == "success"
    assert res["epochs"] == 2
    assert Path(res["checkpoint"]).exists()

    # 2. Generate new choreography with MotionGenerator
    generator = MotionGenerator(checkpoint_path=Path(res["checkpoint"]), device="cpu")
    poses = generator.generate(prompt="High martial arts jump kick", num_frames=12, num_steps=5)
    assert len(poses) == 12
    assert len(poses[0].body) == 18
    assert len(poses[0].left_hand) == 21
    assert len(poses[0].right_hand) == 21
    assert len(poses[0].face) == 68

    # 3. Render generated choreography to control MP4 video
    out_video = tmp_path / "generated_choreography.mp4"
    generator.generate_control_video(
        prompt="High martial arts jump kick",
        output_path=out_video,
        num_frames=12,
        fps=24.0,
        width=320,
        height=240,
    )
    assert out_video.exists()
    assert out_video.stat().st_size > 0
