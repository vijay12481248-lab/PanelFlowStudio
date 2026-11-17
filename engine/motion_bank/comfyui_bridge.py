"""ComfyUI Bridge for Pose-Guided Video Generation (Wan 2.1 Fun-Control).
Connects harvested Motion Bank skeletons and Guide Model choreography to ComfyUI video generation.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from engine.comfyui.client import ComfyUIClient, ComfyUIError


DEFAULT_COMFY_INPUT_DIR = Path(os.environ.get("PANELFLOW_COMFYUI_INPUT_DIR", r"E:\VIJAY SEKAR\ComfyUI\input"))
DEFAULT_COMFY_OUTPUT_DIR = Path(os.environ.get("PANELFLOW_COMFYUI_OUTPUT_DIR", r"E:\VIJAY SEKAR\ComfyUI\output"))


def build_wan21_pose_control_graph(
    image_filename: str,
    control_video_filename: str,
    prompt: str,
    negative_prompt: str = "distorted, extra limbs, bad anatomy, blurry, flickering",
    width: int = 832,
    height: int = 480,
    steps: int = 20,
    cfg: float = 6.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Constructs the ComfyUI API workflow graph for Wan 2.1 Fun-Control I2V with Pose conditioning.
    Adheres strictly to ComfyUI native node interfaces.
    """
    return {
        "1": {
            "inputs": {"unet_name": "wan2.1_i2v_480p_14B_fp8_scaled.safetensors"},
            "class_type": "UNETLoader",
        },
        "2": {
            "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"},
            "class_type": "CLIPLoader",
        },
        "3": {
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
            "class_type": "VAELoader",
        },
        "4": {
            "inputs": {"image": image_filename, "upload": "image"},
            "class_type": "LoadImage",
        },
        "5": {
            "inputs": {"video": control_video_filename, "force_rate": 24, "force_size": f"{width}x{height}"},
            "class_type": "VHS_LoadVideo",
        },
        "6": {
            "inputs": {"text": prompt, "clip": ["2", 0]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": negative_prompt, "clip": ["2", 0]},
            "class_type": "CLIPTextEncode",
        },
        "8": {
            "inputs": {
                "model": ["1", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "start_image": ["4", 0],
                "control_video": ["5", 0],
                "width": width,
                "height": height,
            },
            "class_type": "WanFunControlApply",
        },
        "9": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["8", 0],
                "positive": ["8", 1],
                "negative": ["8", 2],
                "latent_image": ["8", 3],
            },
            "class_type": "KSampler",
        },
        "10": {
            "inputs": {"samples": ["9", 0], "vae": ["3", 0]},
            "class_type": "VAEDecode",
        },
        "11": {
            "inputs": {"filename_prefix": "wan_pose_gen", "images": ["10", 0], "fps": 24},
            "class_type": "VHS_VideoCombine",
        },
    }


class MotionComfyUIBridge:
    """Dispatches pose-guided video generation requests to ComfyUI."""

    def __init__(
        self,
        client: Optional[ComfyUIClient] = None,
        input_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ):
        self.client = client or ComfyUIClient()
        self.input_dir = input_dir or DEFAULT_COMFY_INPUT_DIR
        self.output_dir = output_dir or DEFAULT_COMFY_OUTPUT_DIR
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare_input_media(self, character_image: Path, control_video: Path) -> Tuple[str, str]:
        """Copies or stages input media into ComfyUI's input directory."""
        img_dest = self.input_dir / character_image.name
        if character_image.resolve() != img_dest.resolve():
            shutil.copy2(character_image, img_dest)

        vid_dest = self.input_dir / control_video.name
        if control_video.resolve() != vid_dest.resolve():
            shutil.copy2(control_video, vid_dest)

        return img_dest.name, vid_dest.name

    def render_pose_video(
        self,
        character_image_path: Path,
        control_video_path: Path,
        prompt: str,
        negative_prompt: str = "distorted, blurry, flickering",
        width: int = 832,
        height: int = 480,
        steps: int = 20,
        cfg: float = 6.0,
        seed: int = 42,
        poll_interval_s: float = 2.0,
        timeout_s: float = 600.0,
    ) -> Path:
        """
        Submits the Wan 2.1 Fun-Control workflow to ComfyUI and polls until output video is ready.
        """
        img_name, vid_name = self.prepare_input_media(character_image_path, control_video_path)
        workflow = build_wan21_pose_control_graph(
            image_filename=img_name,
            control_video_filename=vid_name,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=seed,
        )

        prompt_id = self.client.submit_prompt(workflow)
        start_time = time.time()

        while time.time() - start_time < timeout_s:
            hist = self.client.history(prompt_id)
            if prompt_id in hist:
                status = hist[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise ComfyUIError(f"ComfyUI pose video generation failed: {messages}")

                outputs = hist[prompt_id].get("outputs", {})
                for node_id, node_out in outputs.items():
                    gifs = node_out.get("gifs", []) or node_out.get("videos", [])
                    if gifs:
                        filename = gifs[0]["filename"]
                        subfolder = gifs[0].get("subfolder", "")
                        return self.output_dir / subfolder / filename

            time.sleep(poll_interval_s)

        raise TimeoutError(f"ComfyUI pose video generation timed out after {timeout_s} seconds.")
