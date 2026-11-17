"""Manifest of pre-trained models required for DWPose extraction.
Adheres strictly to AGENTS.md constraint:
'Downloads of models/files need the owner's approval with the exact file, size and source first.'
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_MODELS_DIR = Path(os.environ.get("PANELFLOW_DWPOSE_MODEL_DIR", r"E:\VIJAY SEKAR\ComfyUI\models\dwpose"))

DWPOSE_MODELS_MANIFEST: List[Dict[str, Any]] = [
    {
        "id": "yolox_l_onnx",
        "name": "YOLOX-L Person Detector (ONNX)",
        "subfolder": "dwpose",
        "filename": "yolox_l.onnx",
        "repo": "yzd-v/DWPose",
        "url": "https://huggingface.co/yzd-v/DWPose/resolve/main/yolox_l.onnx",
        "size_bytes": 217061730,
        "sha256": "47228ee624640d2d3a31c5ee9ea426c1c8a14b09",
        "required": True,
        "description": "Bounding box detector for human actors across diverse visual contexts.",
    },
    {
        "id": "dw_ll_ucoco_384_onnx",
        "name": "DWPose Whole-Body Keypoint Estimator (ONNX)",
        "subfolder": "dwpose",
        "filename": "dw-ll_ucoco_384.onnx",
        "repo": "yzd-v/DWPose",
        "url": "https://huggingface.co/yzd-v/DWPose/resolve/main/dw-ll_ucoco_384.onnx",
        "size_bytes": 272828038,
        "sha256": "8a32da84a56ea74c2fae62fb462b512c140df949",
        "required": True,
        "description": "Two-stage distilled whole-body pose estimator (18 body, 42 hand, 68 facial landmarks).",
    },
]
