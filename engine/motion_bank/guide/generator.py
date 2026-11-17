"""Motion Generator: Fast DDIM inference for generating skeleton choreography from text prompts."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np
import torch

from engine.motion_bank.guide.text_embed import embed_one
from engine.motion_bank.guide.motion_dit import MotionChoreographerDiT
from engine.motion_bank.guide.trainer import DiffusionSchedule
from engine.motion_bank.models import FramePoseData
from engine.motion_bank.visualizer import render_skeleton_video


class MotionGenerator:
    """Generates continuous whole-body skeleton sequences from text descriptions."""

    def __init__(
        self,
        checkpoint_path: Optional[Path] = None,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ):
        self.device = torch.device(device)
        self.model = MotionChoreographerDiT().to(self.device)
        self.schedule = DiffusionSchedule(timesteps=1000, device=self.device)
        self.embedder = "hash"  # checkpoints from before the embedder was recorded were trained with the hash
        if checkpoint_path and checkpoint_path.is_file():
            ckpt = torch.load(checkpoint_path, map_location=self.device)
            self.model.load_state_dict(ckpt["model_state_dict"])
            self.embedder = ckpt.get("text_embedder", "hash")
        self.model.eval()

    @torch.no_grad()
    def generate(
        self,
        prompt: str,
        num_frames: int = 48,
        fps: float = 24.0,
        start_pose: Optional[FramePoseData] = None,
        num_steps: int = 25,
    ) -> List[FramePoseData]:
        """
        Synthesizes a 133-point whole-body pose sequence using DDIM reverse diffusion.
        Runs in ~0.3-0.5s on RTX 5060 Ti.
        """
        text_embed = embed_one(prompt, self.embedder, dim=256).to(self.device)[None, :]  # (1, 256), same embedder as in training

        start_tensor = None
        if start_pose and start_pose.body:
            sp_arr = np.zeros((133, 3), dtype=np.float32)
            for idx, pt in enumerate(start_pose.body[:18]):
                sp_arr[idx] = pt
            start_tensor = torch.from_numpy(sp_arr).to(self.device)[None, ...]

        # Start from pure noise
        x_t = torch.randn((1, num_frames, 133, 3), device=self.device)

        # DDIM timestep schedule
        step_indices = torch.linspace(self.schedule.timesteps - 1, 0, num_steps, dtype=torch.long, device=self.device)

        for i in range(len(step_indices)):
            t_curr = step_indices[i].repeat(1)
            t_prev = step_indices[i + 1].repeat(1) if i + 1 < len(step_indices) else None

            pred_noise = self.model(x_t, t_curr, text_embed, start_pose=start_tensor)

            # DDIM update step
            a_curr = self.schedule.alphas_cumprod[t_curr[0]]
            x_0_pred = (x_t - torch.sqrt(1.0 - a_curr) * pred_noise) / torch.sqrt(a_curr)
            # Clip coordinates to plausible normalized range
            x_0_pred = torch.clamp(x_0_pred, 0.0, 1.0)

            if t_prev is not None:
                a_prev = self.schedule.alphas_cumprod[t_prev[0]]
                dir_xt = torch.sqrt(1.0 - a_prev) * pred_noise
                x_t = torch.sqrt(a_prev) * x_0_pred + dir_xt
            else:
                x_t = x_0_pred

        # Convert final tensor to FramePoseData list
        out_poses_np = x_t.squeeze(0).cpu().numpy()  # (num_frames, 133, 3)
        result_frames: List[FramePoseData] = []

        for frame_idx in range(num_frames):
            ts = frame_idx / fps
            kpts = out_poses_np[frame_idx]

            # Partition into OpenPose / DWPose components
            body = [(float(kpts[j, 0]), float(kpts[j, 1]), float(kpts[j, 2])) for j in range(18)]
            left_hand = [(float(kpts[j, 0]), float(kpts[j, 1]), float(kpts[j, 2])) for j in range(18, 39)]
            right_hand = [(float(kpts[j, 0]), float(kpts[j, 1]), float(kpts[j, 2])) for j in range(39, 60)]
            face = [(float(kpts[j, 0]), float(kpts[j, 1]), float(kpts[j, 2])) for j in range(60, 128)]

            # Bounding box from body keypoints
            xs = [p[0] for p in body if p[2] > 0.1]
            ys = [p[1] for p in body if p[2] > 0.1]
            bbox = (min(xs), min(ys), max(xs), max(ys)) if xs and ys else (0.2, 0.1, 0.8, 0.9)

            result_frames.append(
                FramePoseData(
                    frame_index=frame_idx,
                    timestamp_sec=round(ts, 3),
                    body=body,
                    left_hand=left_hand,
                    right_hand=right_hand,
                    face=face,
                    bbox=bbox,
                )
            )

        return result_frames

    def generate_control_video(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 48,
        fps: float = 24.0,
        width: int = 960,
        height: int = 544,
    ) -> Path:
        """Generates pose sequence and renders directly to an OpenPose control MP4 video."""
        poses = self.generate(prompt=prompt, num_frames=num_frames, fps=fps)
        return render_skeleton_video(
            frames_poses=poses,
            output_path=output_path,
            fps=fps,
            width=width,
            height=height,
            background="black",
        )
