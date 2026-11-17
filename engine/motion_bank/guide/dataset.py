"""Dataset loader for Motion Bank: paired (action_text, skeleton_trajectory) sequences."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import torch
from torch.utils.data import Dataset

from engine.motion_bank.models import MotionRecord
from engine.motion_bank.guide.text_embed import embed_hash, embed_texts
from engine.motion_bank.storage import MotionBankStorage


def embed_text_deterministic(text: str, dim: int = 256) -> torch.Tensor:
    """The offline hash embedding (kept under its old name; see text_embed.py for the embedders)."""
    return embed_hash(text, dim)


class MotionBankDataset(Dataset):
    """PyTorch Dataset loading kinematic motions from safetensors with text embeddings."""

    def __init__(
        self,
        storage: MotionBankStorage,
        target_seq_len: int = 64,
        text_dim: int = 256,
        include_synthetic: bool = False,
        embedder: str = "hash",
        random_window: bool = False,
    ):
        self.storage = storage
        self.target_seq_len = target_seq_len
        self.text_dim = text_dim
        records = self.storage.list_motions(limit=1000)
        # Fake skeletons (tests/demos) teach the guide nothing real; keep them out unless asked for.
        self.records: List[MotionRecord] = [r for r in records if include_synthetic or not r.metadata.get("synthetic")]
        self.embedder = embedder
        self.random_window = random_window  # training: a random target_seq_len window of long motions, not always the first frames
        descriptions = [f"{r.action_title} {' '.join(r.action_tags)} {r.action_summary}" for r in self.records]
        self._text_embeds = embed_texts(descriptions, embedder, text_dim) if descriptions else torch.zeros((0, text_dim))

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
                offset = random.randint(0, t_len - self.target_seq_len) if self.random_window else 0
                pose_seq = raw_tensor[offset:offset + self.target_seq_len]
            else:
                # Pad with last frame
                padding = raw_tensor[-1:].repeat(self.target_seq_len - t_len, 1, 1)
                pose_seq = torch.cat([raw_tensor, padding], dim=0)

        text_embed = self._text_embeds[idx]

        return {
            "pose_seq": pose_seq,  # (target_seq_len, 133, 3)
            "text_embed": text_embed,  # (text_dim,)
            "start_pose": pose_seq[0],  # (133, 3)
        }
