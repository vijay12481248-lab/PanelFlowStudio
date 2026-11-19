"""Unified Image Visual Quality Inspector combining CPU CV and Multi-Tile VLM Review."""
from __future__ import annotations

import asyncio
import io
from pathlib import Path
import time
from typing import List, Optional
import cv2
import numpy as np
from PIL import Image

from engine.inspector.decision import QualityDecisionEngine
from engine.inspector.face_engine import OpenFaceEngine
from engine.inspector.schema import DefectRecord, InspectorConfig, QualityDecision
from engine.inspector.topology import SkeletonTopologyValidator
from engine.motion_bank.dwpose_extractor import DWPoseExtractor


class ImageInspector:
    """
    Independent Image Visual Quality Inspector.
    Fuses:
    1. DWPose 133-keypoint skeletal topology (CPU ONNX, Apache 2.0).
    2. OpenCV YuNet + SFace face analysis (CPU, Apache 2.0).
    3. Multi-tile blind VLM hand enumeration and text checking (Ollama qwen3.5:9b).
    """

    def __init__(
        self,
        config: Optional[InspectorConfig] = None,
        judges: Optional[list] = None,
    ):
        self.config = config or InspectorConfig()
        self.judges = judges
        if self.judges is None and self.config.enable_vlm:
            try:
                from engine.llm.registry import llm_registry
                from engine.original.judges import OllamaJudge
                ollama = llm_registry.get_ollama_provider()
                if ollama:
                    self.judges = [OllamaJudge(provider=ollama, name="qwen3.5:9b")]
            except Exception:
                self.judges = []
        if self.judges is None:
            self.judges = []

        self.dwpose = DWPoseExtractor()
        self.face_engine = OpenFaceEngine(conf_threshold=self.config.face_confidence)
        self.topology_validator = SkeletonTopologyValidator()
        self.decision_engine = QualityDecisionEngine(self.config)

    def is_ready(self) -> bool:
        """Checks if local ONNX and OpenCV model weights are present."""
        return self.dwpose.is_ready() and self.face_engine.is_ready()

    def inspect_image(
        self,
        image_data: bytes | str | Path,
        prompt: str = "",
        expected_people: Optional[int] = None,
    ) -> QualityDecision:
        """Alias for inspect(), providing uniform method naming."""
        return self.inspect(image_data=image_data, prompt=prompt, expected_people=expected_people)

    def inspect(
        self,
        image_data: bytes | str | Path,
        prompt: str = "",
        expected_people: Optional[int] = None,
    ) -> QualityDecision:
        """
        Executes full inspection across an image PNG/JPEG buffer or file path.
        """
        t0 = time.monotonic()
        all_defects: List[DefectRecord] = []

        if isinstance(image_data, (str, Path)):
            with open(image_data, "rb") as f:
                image_bytes = f.read()
        else:
            image_bytes = image_data

        # 1. Decode image bytes to NumPy arrays
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_rgb = np.array(pil_img)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        # 2. Stage 1: Computer Vision on CPU (Zero VRAM impact)
        faces = []
        pose = None
        people_count = expected_people

        if self.config.enable_face_check and self.face_engine.is_ready():
            try:
                faces = self.face_engine.detect_and_embed(img_bgr)
            except Exception:
                faces = []

        if self.config.enable_cv_topology and self.dwpose.is_ready():
            try:
                pose = self.dwpose.extract_frame_pose(img_rgb, frame_index=0, timestamp_sec=0.0)
                if pose and pose.body:
                    if people_count is None:
                        people_count = 1
                    top_defects = self.topology_validator.validate_pose(pose, people_count=people_count)
                    all_defects.extend(top_defects)
            except Exception:
                pass

        if faces and self.config.enable_face_check:
            face_defects = self.face_engine.check_face_defects(
                faces,
                people_count=people_count,
                identity_threshold=self.config.identity_similarity_threshold,
            )
            all_defects.extend(face_defects)

        # 3. Stage 2: Semantic VLM Review (if judges provided)
        hands_count = None
        if self.config.enable_vlm and self.judges:
            try:
                from engine.original.anatomy.review import review_picture
                report = asyncio.run(review_picture(self.judges, image_bytes, prompt))
                if report.people is not None:
                    people_count = report.people

                # Map confirmed VLM defects to DefectRecords
                for vlm_d in report.confirmed:
                    # Severity mapping
                    sev = "severe" if vlm_d.kind in ("extra_hands", "merged_bodies") else "moderate"
                    all_defects.append(
                        DefectRecord(
                            category=vlm_d.kind,
                            confidence=0.92,
                            severity=sev,
                            evidence=vlm_d.detail,
                            tile=vlm_d.tile,
                            recommended_action="inpaint" if vlm_d.kind in ("extra_hands", "stray_text", "duplicate_object") else "redraw",
                        )
                    )
                for vlm_s in report.suspected:
                    all_defects.append(
                        DefectRecord(
                            category=vlm_s.kind,
                            confidence=0.65,
                            severity="minor",
                            evidence=f"Suspected: {vlm_s.detail}",
                            tile=vlm_s.tile,
                            recommended_action="inpaint" if vlm_s.kind in ("extra_hands", "stray_text", "duplicate_object") else "redraw",
                        )
                    )
            except Exception:
                pass

        elapsed = time.monotonic() - t0
        return self.decision_engine.evaluate(
            defects=all_defects,
            people_count=people_count,
            faces_count=len(faces),
            hands_count=hands_count,
            seconds=elapsed,
        )

    # Alias for API uniformity
    inspect_image = inspect

