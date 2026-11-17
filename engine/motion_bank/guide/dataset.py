"""Dataset loader for Motion Bank: paired (action_text, skeleton_trajectory) sequences."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import torch
from torch.utils.data import Dataset

from engine.motion_bank.models import MotionRecord
from engine.motion_bank.storage import MotionBankStorage


def embed_text_deterministic(text: str, dim: int = 256) -> torch.Tensor:
    """
    Deterministic semantic hash embedding for action prompts.
    Provides offline, local-first zero-latency vectorization without requiring external weights.
    """
    words = text.lower().replace(",", " ").split()
    vec = torch.zeros(dim, dtype=torch.float32)
    for word in words:
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        # Distribute word hash into multiple dimensions with sinusoidal projection
        for i in range(8):
            idx = (h >> (i * 8)) % dim
            sign = 1.0 if ((h >> (i * 8 + 4)) & 1) else -1.0
            vec[idx] += sign
    norm = torch.norm(vec)
    return vec / max(1e-5, float(norm))


class MotionBankDataset(Dataset):
    """PyTorch Dataset loading kinematic motions from safetensors with text embeddings."""

    def __init__(
        self,
        storage: MotionBankStorage,
        target_seq_len: int = 64,
        text_dim: int = 256,
        include_synthetic: bool = False,
    ):
        self.storage = storage
        self.target_seq_len = target_seq_len
        self.text_dim = text_dim
        records = self.storage.list_motions(limit=1000)
        # Fake skeletons (tests/demos) teach the guide nothing real; keep them out unless asked for.
        self.records: List[MotionRecord] = [r for r in records if include_synthetic or not r.metadata.get("synthetic")]

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        rec = self.records[idx]
        kp_path = Path(rec.keypoints_path)

        if not kp_path.is_file():
            # Fallback zero tensor if file missing
            pose_seq = torch.zeros((self.target_seq_len, 133, 3), dtype=torch.float32)
        else:
            raw_tensor = self.storage.load_keypoints_tensor(kp_path)  # (T, 133, 3)
            t_len = raw_tensor.shape[0]

            if t_len >= self.target_seq_len:
                pose_seq = raw_tensor[:self.target_seq_len]
            else:
                # Pad with last frame
                padding = raw_tensor[-1:].repeat(self.target_seq_len - t_len, 1, 1)
                pose_seq = torch.cat([raw_tensor, padding], dim=0)

        # Generate text embedding from title + tags
        action_desc = f"{rec.action_title} {' '.join(rec.action_tags)} {rec.action_summary}"
        text_embed = embed_text_deterministic(action_desc, dim=self.text_dim)

        return {
            "pose_seq": pose_seq,  # (target_seq_len, 133, 3)
            "text_embed": text_embed,  # (text_dim,)
            "start_pose": pose_seq[0],  # (133, 3)
        }
