"""Commercial-friendly Face Detection, Landmarking and Identity Matching using OpenCV YuNet + SFace (Apache 2.0)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np

from engine.inspector.schema import DefectRecord, FaceDetectionResult

DEFAULT_OPENCV_DIR = Path(os.environ.get("OPENCV_MODEL_DIR", r"E:\VIJAY SEKAR\ComfyUI\models\opencv"))
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
SFACE_FILENAME = "face_recognition_sface_2021dec.onnx"


class OpenFaceEngine:
    """
    Open-source, 100% commercial-grade face analysis suite.
    Uses YuNet (Apache 2.0) for face/landmark detection and SFace (Apache 2.0) for 128-dim embeddings.
    Runs on CPU with 0 MB GPU VRAM cost.
    """

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        conf_threshold: float = 0.60,
        nms_threshold: float = 0.30,
    ):
        self.models_dir = models_dir or DEFAULT_OPENCV_DIR
        self.yunet_path = self.models_dir / YUNET_FILENAME
        self.sface_path = self.models_dir / SFACE_FILENAME
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold

        self._detector: Optional[cv2.FaceDetectorYN] = None
        self._recognizer: Optional[cv2.FaceRecognizerSF] = None

    def is_ready(self) -> bool:
        """Verify model weights are present on disk."""
        return self.yunet_path.is_file() and self.sface_path.is_file()

    def _ensure_loaded(self, width: int = 640, height: int = 640) -> None:
        if not self.is_ready():
            raise FileNotFoundError(
                f"OpenCV face models missing. Expected:\n"
                f"YuNet: {self.yunet_path}\n"
                f"SFace: {self.sface_path}"
            )
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(
                str(self.yunet_path),
                "",
                (width, height),
                score_threshold=self.conf_threshold,
                nms_threshold=self.nms_threshold,
                top_k=50,
            )
        else:
            self._detector.setInputSize((width, height))

        if self._recognizer is None:
            self._recognizer = cv2.FaceRecognizerSF.create(str(self.sface_path), "")

    def detect_and_embed(self, image_bgr: np.ndarray) -> List[FaceDetectionResult]:
        """
        Detects all faces, extracts 5 landmarks, aligns crops, and computes 128-dim embeddings.
        Returns list of FaceDetectionResult with normalized coordinates.
        """
        h, w = image_bgr.shape[:2]
        self._ensure_loaded(w, h)

        _, raw_faces = self._detector.detect(image_bgr)
        if raw_faces is None or len(raw_faces) == 0:
            return []

        results: List[FaceDetectionResult] = []
        for face in raw_faces:
            # YuNet output layout:
            # 0-3: bbox (x, y, w, h)
            # 4-13: 5 landmarks (x, y) for right eye, left eye, nose tip, right mouth, left mouth
            # 14: confidence score
            fx, fy, fw, fh = face[0:4]
            conf = float(face[14])

            # Normalised bbox (x1, y1, x2, y2)
            x1 = max(0.0, float(fx) / w)
            y1 = max(0.0, float(fy) / h)
            x2 = min(1.0, float(fx + fw) / w)
            y2 = min(1.0, float(fy + fh) / h)

            # Extract 5 landmarks
            landmarks: List[Tuple[float, float]] = []
            for i in range(5):
                lx = float(face[4 + i * 2]) / w
                ly = float(face[5 + i * 2]) / h
                landmarks.append((lx, ly))

            # Align face crop and extract SFace embedding
            aligned_face = self._recognizer.alignCrop(image_bgr, face)
            feat = self._recognizer.feature(aligned_face)
            normed_feat = (feat / (np.linalg.norm(feat) + 1e-8)).flatten().tolist()

            results.append(
                FaceDetectionResult(
                    bbox=(x1, y1, x2, y2),
                    confidence=conf,
                    landmarks=landmarks,
                    embedding=normed_feat,
                )
            )

        return results

    def compute_similarity(self, feat_a: List[float], feat_b: List[float]) -> float:
        """Computes cosine similarity between two 128-dim feature vectors."""
        a = np.asarray(feat_a, dtype=np.float32)
        b = np.asarray(feat_b, dtype=np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom < 1e-8:
            return 0.0
        return float(np.dot(a, b) / denom)

    def check_face_defects(
        self,
        faces: List[FaceDetectionResult],
        people_count: Optional[int] = None,
        identity_threshold: float = 0.82,
    ) -> List[DefectRecord]:
        """
        Inspects detected faces for:
        1. Extra heads: Face count exceeds person count.
        2. Duplicate characters: Two distinct faces have high cosine similarity.
        3. Distorted faces: Unnatural aspect ratios or collapsed facial landmarks.
        """
        defects: List[DefectRecord] = []
        n_faces = len(faces)

        # 1. Extra heads check
        if people_count is not None and people_count > 0:
            if n_faces > people_count:
                extra = n_faces - people_count
                defects.append(
                    DefectRecord(
                        category="extra_head",
                        confidence=0.88,
                        severity="severe" if extra > 1 else "moderate",
                        evidence=f"Detected {n_faces} faces for {people_count} person bodies ({extra} extra head(s)).",
                        recommended_action="inpaint",
                        details={"face_count": n_faces, "people_count": people_count},
                    )
                )

        # 2. Intra-frame duplicate character check
        if n_faces >= 2:
            for i in range(n_faces):
                for j in range(i + 1, n_faces):
                    feat_a = faces[i].embedding
                    feat_b = faces[j].embedding
                    if feat_a and feat_b:
                        sim = self.compute_similarity(feat_a, feat_b)
                        if sim >= identity_threshold:
                            defects.append(
                                DefectRecord(
                                    category="duplicate_character",
                                    bbox=faces[j].bbox,
                                    confidence=round(sim, 3),
                                    severity="moderate",
                                    evidence=f"Faces at {faces[i].bbox} and {faces[j].bbox} share high identity similarity ({sim:.2f} >= {identity_threshold}).",
                                    recommended_action="inpaint",
                                    details={"sim": sim, "pair": [i, j]},
                                )
                            )

        # 3. Biometric face ratio & distortion check
        for face in faces:
            x1, y1, x2, y2 = face.bbox
            fw = x2 - x1
            fh = y2 - y1
            if fw > 0.03 and fh > 0.03:
                aspect = fw / (fh + 1e-6)
                if aspect > 2.2 or aspect < 0.45:
                    defects.append(
                        DefectRecord(
                            category="distorted_face",
                            bbox=face.bbox,
                            confidence=0.85,
                            severity="moderate",
                            evidence=f"Unnatural face aspect ratio ({aspect:.2f}); distorted proportions.",
                            recommended_action="inpaint",
                            details={"aspect_ratio": aspect},
                        )
                    )
                elif len(face.landmarks) >= 2:
                    # Eye-to-eye horizontal distance check
                    eye_dx = abs(face.landmarks[0][0] - face.landmarks[1][0])
                    eye_dy = abs(face.landmarks[0][1] - face.landmarks[1][1])
                    eye_dist = (eye_dx**2 + eye_dy**2) ** 0.5
                    if eye_dist < 0.10 * fw:
                        defects.append(
                            DefectRecord(
                                category="distorted_face",
                                bbox=face.bbox,
                                confidence=0.89,
                                severity="severe",
                                evidence=f"Collapsed eye distance ({eye_dist:.3f} < 0.10 * {fw:.3f}); melted face geometry.",
                                recommended_action="inpaint",
                                details={"eye_dist": eye_dist, "face_width": fw},
                            )
                        )

        return defects
