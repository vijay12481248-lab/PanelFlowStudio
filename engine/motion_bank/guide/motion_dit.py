"""Motion-DiT: Lightweight Kinematic Diffusion Transformer (The Choreographer).
Generates whole-body skeleton trajectories from text prompts and initial pose constraints.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple
import torch
import torch.nn as nn
import torch.nn.functional as F


def get_sinusoidal_encoding(timesteps: torch.Tensor, dim: int) -> torch.Tensor:
    """Computes sinusoidal positional embeddings for timesteps."""
    half_dim = dim // 2
    emb = math.log(10000) / (half_dim - 1)
    emb = torch.exp(torch.arange(half_dim, dtype=torch.float32, device=timesteps.device) * -emb)
    emb = timesteps.float()[:, None] * emb[None, :]
    emb = torch.cat([torch.sin(emb), torch.cos(emb)], dim=-1)
    if dim % 2 == 1:
        emb = F.pad(emb, (0, 1))
    return emb


class DiTBlock(nn.Module):
    """Diffusion Transformer Block with adaptive scale and shift conditioning."""

    def __init__(self, hidden_dim: int, num_heads: int, mlp_ratio: float = 4.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(hidden_dim, elementwise_affine=False, eps=1e-6)
        self.attn = nn.MultiheadAttention(embed_dim=hidden_dim, num_heads=num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(hidden_dim, elementwise_affine=False, eps=1e-6)

        mlp_hidden_dim = int(hidden_dim * mlp_ratio)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_dim, mlp_hidden_dim),
            nn.GELU(),
            nn.Linear(mlp_hidden_dim, hidden_dim),
        )

        # Modulation: scale, shift, gate for self-attn and mlp
        self.adaLN_modulation = nn.Sequential(
            nn.SiLU(),
            nn.Linear(hidden_dim, 6 * hidden_dim, bias=True),
        )

    def forward(self, x: torch.Tensor, c: torch.Tensor) -> torch.Tensor:
        # c has shape (B, hidden_dim)
        mod = self.adaLN_modulation(c)[:, None, :]  # (B, 1, 6*hidden_dim)
        shift_msa, scale_msa, gate_msa, shift_mlp, scale_mlp, gate_mlp = mod.chunk(6, dim=-1)

        # Self-attention branch
        normed_x = self.norm1(x) * (1 + scale_msa) + shift_msa
        attn_out, _ = self.attn(normed_x, normed_x, normed_x)
        x = x + gate_msa * attn_out

        # MLP branch
        normed_mlp = self.norm2(x) * (1 + scale_mlp) + shift_mlp
        x = x + gate_mlp * self.mlp(normed_mlp)
        return x


class MotionChoreographerDiT(nn.Module):
    """
    Lightweight DiT model predicting kinematic velocity or noise for 133-keypoint poses.
    Hidden dimension: 256, 6 layers, ~22M parameters.
    """

    def __init__(
        self,
        num_keypoints: int = 133,
        coords_per_kp: int = 3,
        max_seq_len: int = 128,
        hidden_dim: int = 256,
        depth: int = 6,
        num_heads: int = 8,
        text_dim: int = 256,
    ):
        super().__init__()
        self.num_keypoints = num_keypoints
        self.coords_per_kp = coords_per_kp
        self.input_dim = num_keypoints * coords_per_kp  # 133 * 3 = 399
        self.hidden_dim = hidden_dim
        self.max_seq_len = max_seq_len

        # Pose projection
        self.pose_embed = nn.Linear(self.input_dim, hidden_dim)

        # Frame positional embedding
        self.pos_embed = nn.Parameter(torch.zeros(1, max_seq_len, hidden_dim))

        # Timestep conditioning
        self.t_embed = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

        # Text conditioning projection
        self.cond_proj = nn.Sequential(
            nn.Linear(text_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

        # Transformer blocks
        self.blocks = nn.ModuleList([
            DiTBlock(hidden_dim=hidden_dim, num_heads=num_heads)
            for _ in range(depth)
        ])

        # Final projection to kinematic outputs
        self.final_norm = nn.LayerNorm(hidden_dim, eps=1e-6)
        self.final_proj = nn.Linear(hidden_dim, self.input_dim)

        self._init_weights()

    def _init_weights(self):
        # Initialize positional embedding
        nn.init.normal_(self.pos_embed, std=0.02)
        # Initialize final projection with zeros (standard DiT practice)
        nn.init.zeros_(self.final_proj.weight)
        nn.init.zeros_(self.final_proj.bias)

    def forward(
        self,
        x_t: torch.Tensor,
        timesteps: torch.Tensor,
        text_embed: torch.Tensor,
        start_pose: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x_t: Noisy pose tensor (B, T, 133, 3) or (B, T, 399)
            timesteps: Diffusion timesteps (B,)
            text_embed: Action text embedding (B, text_dim)
            start_pose: Optional initial pose (B, 133, 3) to guide continuation
        Returns:
            Predicted noise / velocity (B, T, 133, 3)
        """
        B, T = x_t.shape[0], x_t.shape[1]
        x_flat = x_t.reshape(B, T, -1)

        # 1. Embed pose coordinates and add frame position
        h = self.pose_embed(x_flat) + self.pos_embed[:, :T, :]

        # 2. Embed conditioning (timestep + text)
        t_emb = self.t_embed(get_sinusoidal_encoding(timesteps, self.hidden_dim))
        c_emb = self.cond_proj(text_embed)
        c = t_emb + c_emb

        # Optional start pose conditioning
        if start_pose is not None:
            sp_flat = start_pose.reshape(B, 1, -1)
            sp_emb = self.pose_embed(sp_flat).squeeze(1)
            c = c + sp_emb

        # 3. Transformer backbone
        for block in self.blocks:
            h = block(h, c)

        # 4. Final output
        h = self.final_norm(h)
        out = self.final_proj(h)
        return out.reshape(B, T, self.num_keypoints, self.coords_per_kp)
