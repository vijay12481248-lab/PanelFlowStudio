"""Trainer for Motion-DiT: Local kinematic motion diffusion training loop."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Optional
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from engine.motion_bank.guide.dataset import MotionBankDataset
from engine.motion_bank.guide.motion_dit import MotionChoreographerDiT
from engine.motion_bank.storage import MotionBankStorage


class DiffusionSchedule:
    """Cosine beta schedule for DDPM noise synthesis."""

    def __init__(self, timesteps: int = 1000, device: torch.device = torch.device("cpu")):
        self.timesteps = timesteps
        self.device = device
        # Cosine schedule
        s = 0.008
        steps = timesteps + 1
        x = torch.linspace(0, timesteps, steps, dtype=torch.float32)
        alphas_cumprod = torch.cos(((x / timesteps) + s) / (1 + s) * torch.pi * 0.5) ** 2
        alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
        betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
        self.betas = torch.clip(betas, 0.0001, 0.9999).to(device)
        self.alphas = (1.0 - self.betas).to(device)
        self.alphas_cumprod = torch.cumprod(self.alphas, dim=0).to(device)
        self.sqrt_alphas_cumprod = torch.sqrt(self.alphas_cumprod)
        self.sqrt_one_minus_alphas_cumprod = torch.sqrt(1.0 - self.alphas_cumprod)


class MotionGuideTrainer:
    """Manages local model training on harvested motion trajectories."""

    def __init__(
        self,
        storage: MotionBankStorage,
        output_dir: Path,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ):
        self.storage = storage
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = torch.device(device)
        self.model = MotionChoreographerDiT().to(self.device)
        self.schedule = DiffusionSchedule(timesteps=1000, device=self.device)
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=1e-4, weight_decay=1e-4)
        self.checkpoint_path = self.output_dir / "choreographer_latest.pt"

    def train_epoch(self, dataloader: DataLoader) -> float:
        """Runs a single training epoch and returns mean loss."""
        self.model.train()
        total_loss = 0.0
        count = 0

        for batch in dataloader:
            x_0 = batch["pose_seq"].to(self.device)  # (B, T, 133, 3)
            text_embed = batch["text_embed"].to(self.device)
            start_pose = batch["start_pose"].to(self.device)

            B = x_0.shape[0]
            t = torch.randint(0, self.schedule.timesteps, (B,), device=self.device).long()
            noise = torch.randn_like(x_0)

            # Diffuse x_0 to x_t
            sqrt_a = self.schedule.sqrt_alphas_cumprod[t][:, None, None, None]
            sqrt_one_minus_a = self.schedule.sqrt_one_minus_alphas_cumprod[t][:, None, None, None]
            x_t = sqrt_a * x_0 + sqrt_one_minus_a * noise

            # Predict noise
            pred_noise = self.model(x_t, t, text_embed, start_pose=start_pose)
            loss = nn.functional.mse_loss(pred_noise, noise)

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()

            total_loss += float(loss.item())
            count += 1

        return total_loss / max(1, count)

    def train(self, num_epochs: int = 10, batch_size: int = 16) -> Dict[str, float]:
        """Executes full training session and saves checkpoint."""
        dataset = MotionBankDataset(self.storage)
        if len(dataset) == 0:
            return {"status": "error", "message": "No motions in Motion Bank to train on."}

        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)
        start_time = time.time()
        losses = []

        for epoch in range(1, num_epochs + 1):
            loss = self.train_epoch(dataloader)
            losses.append(loss)

        # Save checkpoint
        self.save_checkpoint()
        duration = round(time.time() - start_time, 2)
        return {
            "status": "success",
            "epochs": num_epochs,
            "final_loss": round(losses[-1], 5) if losses else 0.0,
            "duration_sec": duration,
            "checkpoint": str(self.checkpoint_path.resolve()),
        }

    def save_checkpoint(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.checkpoint_path.with_suffix(".pt.tmp")
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
            },
            str(tmp_path),
        )
        if self.checkpoint_path.exists():
            try:
                self.checkpoint_path.unlink()
            except OSError:
                pass
        try:
            tmp_path.replace(self.checkpoint_path)
        except OSError:
            import shutil
            shutil.copy2(tmp_path, self.checkpoint_path)
            try:
                tmp_path.unlink()
            except OSError:
                pass

    def load_checkpoint(self) -> bool:
        if self.checkpoint_path.is_file():
            ckpt = torch.load(self.checkpoint_path, map_location=self.device)
            self.model.load_state_dict(ckpt["model_state_dict"])
            return True
        return False
