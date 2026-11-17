"""Motion Bank Storage: SQLite metadata index and safetensors kinematic tensor persistence."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import torch
from safetensors.torch import load_file, save_file

from engine.motion_bank.models import FramePoseData, MotionRecord


class MotionBankStorage:
    """Manages the persistence of motion metadata in SQLite and kinematics in safetensors."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "motion_bank.db"
        self._init_db()

    def _init_db(self) -> None:
        """Initializes database schema."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS motions (
                    id TEXT PRIMARY KEY,
                    source_uri TEXT,
                    action_title TEXT,
                    action_summary TEXT,
                    action_tags TEXT,
                    duration_sec REAL,
                    fps REAL,
                    frame_count INTEGER,
                    width INTEGER,
                    height INTEGER,
                    actor_track_id INTEGER,
                    keypoints_path TEXT,
                    control_video_path TEXT,
                    preview_video_path TEXT,
                    thumbnail_path TEXT,
                    created_at REAL,
                    metadata_json TEXT
                )
                """
            )
            conn.commit()

    def save_motion(
        self,
        record: MotionRecord,
        frames_poses: Optional[List[FramePoseData]] = None,
    ) -> MotionRecord:
        """Saves a MotionRecord and optionally serializes the kinematic keypoints tensor to safetensors."""
        # If keypoint objects are provided and safetensors file does not exist, save them
        if frames_poses is not None:
            kp_path = Path(record.keypoints_path)
            kp_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_keypoints_safetensors(frames_poses, kp_path)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO motions (
                    id, source_uri, action_title, action_summary, action_tags,
                    duration_sec, fps, frame_count, width, height, actor_track_id,
                    keypoints_path, control_video_path, preview_video_path, thumbnail_path,
                    created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.source_uri,
                    record.action_title,
                    record.action_summary,
                    json.dumps(record.action_tags),
                    record.duration_sec,
                    record.fps,
                    record.frame_count,
                    record.resolution[0],
                    record.resolution[1],
                    record.actor_track_id,
                    record.keypoints_path,
                    record.control_video_path,
                    record.preview_video_path,
                    record.thumbnail_path,
                    record.created_at,
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()

        return record

    def get_motion(self, motion_id: str) -> Optional[MotionRecord]:
        """Retrieves a MotionRecord by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM motions WHERE id = ?", (motion_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def list_motions(self, tag: Optional[str] = None, limit: int = 100) -> List[MotionRecord]:
        """Lists stored motions, optionally filtered by tag."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if tag:
                cursor.execute(
                    "SELECT * FROM motions WHERE action_tags LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{tag}%", limit),
                )
            else:
                cursor.execute("SELECT * FROM motions ORDER BY created_at DESC LIMIT ?", (limit,))
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def search_motions(self, query: str, limit: int = 50) -> List[MotionRecord]:
        """Full text substring search on title, summary, and tags."""
        term = f"%{query}%"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM motions
                WHERE action_title LIKE ? OR action_summary LIKE ? OR action_tags LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (term, term, term, limit),
            )
            return [self._row_to_record(r) for r in cursor.fetchall()]

    def delete_motion(self, motion_id: str) -> Optional[MotionRecord]:
        """Removes the row and returns it (None when unknown). Files are the caller's business."""
        rec = self.get_motion(motion_id)
        if rec is None:
            return None
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM motions WHERE id = ?", (motion_id,))
            conn.commit()
        return rec

    def update_motion(
        self,
        motion_id: str,
        action_title: Optional[str] = None,
        action_summary: Optional[str] = None,
        action_tags: Optional[List[str]] = None,
    ) -> Optional[MotionRecord]:
        """Renames / re-describes / re-tags a motion; fields left as None are kept."""
        rec = self.get_motion(motion_id)
        if rec is None:
            return None
        if action_title is not None:
            rec.action_title = action_title
        if action_summary is not None:
            rec.action_summary = action_summary
        if action_tags is not None:
            rec.action_tags = action_tags
        return self.save_motion(rec)

    def load_keypoints_tensor(self, keypoints_path: Path) -> torch.Tensor:
        """Loads kinematic tensor [T, 133, 3] from safetensors."""
        tensors = load_file(str(keypoints_path))
        return tensors["keypoints"]

    def _save_keypoints_safetensors(self, frames_poses: List[FramePoseData], output_path: Path) -> None:
        """Serializes frames poses into a [T, 133, 3] float32 tensor saved as safetensors."""
        num_frames = len(frames_poses)
        # 133 keypoints: 18 body + 21 left hand + 21 right hand + 73/68 face
        tensor_data = np.zeros((num_frames, 133, 3), dtype=np.float32)

        for i, f in enumerate(frames_poses):
            if f.body:
                b_len = min(18, len(f.body))
                tensor_data[i, :b_len, :] = np.array(f.body[:b_len], dtype=np.float32)
            if f.left_hand:
                lh_len = min(21, len(f.left_hand))
                tensor_data[i, 18:18 + lh_len, :] = np.array(f.left_hand[:lh_len], dtype=np.float32)
            if f.right_hand:
                rh_len = min(21, len(f.right_hand))
                tensor_data[i, 39:39 + rh_len, :] = np.array(f.right_hand[:rh_len], dtype=np.float32)
            if f.face:
                fc_len = min(73, len(f.face))
                tensor_data[i, 60:60 + fc_len, :] = np.array(f.face[:fc_len], dtype=np.float32)

        torch_tensor = torch.from_numpy(tensor_data)
        save_file({"keypoints": torch_tensor}, str(output_path))

    def _row_to_record(self, row: sqlite3.Row) -> MotionRecord:
        return MotionRecord(
            id=row["id"],
            source_uri=row["source_uri"],
            action_title=row["action_title"],
            action_summary=row["action_summary"] or "",
            action_tags=json.loads(row["action_tags"] or "[]"),
            duration_sec=row["duration_sec"],
            fps=row["fps"],
            frame_count=row["frame_count"],
            resolution=(row["width"], row["height"]),
            actor_track_id=row["actor_track_id"],
            keypoints_path=row["keypoints_path"],
            control_video_path=row["control_video_path"],
            preview_video_path=row["preview_video_path"],
            thumbnail_path=row["thumbnail_path"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
