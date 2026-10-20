"""Approved ComfyUI workflow registry with checksum verification."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .client import ComfyUIClient, ComfyUIError
from engine.security.paths import read_contained_bytes, resolve_contained_path


_WORKFLOW_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_REGISTRY_FILE = Path(__file__).with_name("workflow_registry.json")
_MAX_WORKFLOW_BYTES = 4 * 1024 * 1024
_REQUIRED_PATCH_SLOTS = frozenset({"prompt", "negative_prompt", "seed", "width", "height", "filename_prefix"})


class WorkflowRegistryError(RuntimeError):
    """Raised when an approved workflow is unavailable or has changed."""


class ComfyWorkflowRegistry:
    def __init__(self, client: ComfyUIClient | None = None) -> None:
        self.client = client or ComfyUIClient()
        self._entries = {entry["id"]: entry for entry in json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))}

    def list(self) -> list[dict[str, Any]]:
        result = []
        for entry in self._entries.values():
            try:
                workflow, checksum = self.load(entry["id"])
                preflight = self.preflight(entry["id"])
                result.append({**entry, **preflight, "available": True, "verified_sha256": checksum, "node_count": len(workflow)})
            except (WorkflowRegistryError, ComfyUIError) as exc:
                result.append({**entry, "available": False, "error": str(exc)})
        return result

    def load(self, workflow_id: str) -> tuple[dict[str, Any], str]:
        if not _WORKFLOW_ID.fullmatch(workflow_id) or workflow_id not in self._entries:
            raise WorkflowRegistryError("Unknown or invalid approved workflow id")
        entry = self._entries[workflow_id]
        root = self.client.api_workflow_root()
        if root is None:
            raise WorkflowRegistryError("ComfyUI API workflow directory is not configured or unavailable")
        try:
            resolve_contained_path(root, entry["filename"], must_be_file=True)
            raw = read_contained_bytes(root, entry["filename"], max_bytes=_MAX_WORKFLOW_BYTES)
        except OverflowError as exc:
            raise WorkflowRegistryError(f"Approved workflow exceeds size limit: {entry['filename']}") from exc
        except (ValueError, FileNotFoundError, OSError) as exc:
            raise WorkflowRegistryError(f"Approved workflow file is missing or unsafe: {entry['filename']}") from exc
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != entry["sha256"]:
            raise WorkflowRegistryError(f"Workflow checksum mismatch for {workflow_id}")
        try:
            workflow = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkflowRegistryError(f"Workflow JSON is invalid for {workflow_id}") from exc
        if not isinstance(workflow, dict) or not workflow:
            raise WorkflowRegistryError(f"Workflow {workflow_id} is empty or not an API-format mapping")
        self._validate_patch_slots(workflow_id, workflow, entry)
        return workflow, checksum

    @staticmethod
    def _validate_patch_slots(
        workflow_id: str,
        workflow: dict[str, Any],
        entry: dict[str, Any],
    ) -> None:
        slots = entry.get("patch_slots")
        if not isinstance(slots, dict) or set(slots) != _REQUIRED_PATCH_SLOTS:
            raise WorkflowRegistryError(
                f"Workflow {workflow_id} must declare exact patch slots: {sorted(_REQUIRED_PATCH_SLOTS)}"
            )
        for slot_name, slot in slots.items():
            if not isinstance(slot, dict) or set(slot) != {"node_id", "input", "class_type"}:
                raise WorkflowRegistryError(f"Workflow {workflow_id} patch slot {slot_name} is invalid")
            node = workflow.get(str(slot["node_id"]))
            if not isinstance(node, dict):
                raise WorkflowRegistryError(f"Workflow {workflow_id} patch slot {slot_name} node is missing")
            if node.get("class_type") != slot["class_type"]:
                raise WorkflowRegistryError(
                    f"Workflow {workflow_id} patch slot {slot_name} class_type does not match approved metadata"
                )
            inputs = node.get("inputs")
            if not isinstance(inputs, dict) or slot["input"] not in inputs:
                raise WorkflowRegistryError(f"Workflow {workflow_id} patch slot {slot_name} input is missing")

        policy = entry.get("dimension_policy")
        if (
            not isinstance(policy, dict)
            or set(policy) != {"mode", "min", "max", "multiple_of"}
            or policy.get("mode") != "exact"
            or not all(isinstance(policy.get(key), int) for key in ("min", "max", "multiple_of"))
            or policy["min"] < 1
            or policy["max"] < policy["min"]
            or policy["multiple_of"] < 1
        ):
            raise WorkflowRegistryError(f"Workflow {workflow_id} requires an exact dimension policy")

    def preflight(self, workflow_id: str) -> dict[str, Any]:
        workflow, checksum = self.load(workflow_id)
        entry = self._entries[workflow_id]
        capabilities = self.client.capabilities()
        installed_nodes = set(capabilities.get("node_names", []))
        missing_nodes = sorted(set(entry.get("required_nodes", [])) - installed_nodes)
        installed_models = {
            filename
            for filenames in capabilities.get("models", {}).values()
            for filename in filenames
        }
        missing_models = sorted(set(entry.get("model_files", [])) - installed_models)
        return {
            "workflow_id": workflow_id,
            "workflow_sha256": checksum,
            "ready": not missing_nodes and not missing_models and bool(capabilities.get("available")),
            "missing_nodes": missing_nodes,
            "missing_models": missing_models,
            "node_count": len(workflow),
        }

    def metadata(self, workflow_id: str) -> dict[str, Any]:
        if workflow_id not in self._entries:
            raise WorkflowRegistryError("Unknown approved workflow id")
        entry = dict(self._entries[workflow_id])
        _, checksum = self.load(workflow_id)
        entry["verified_sha256"] = checksum
        return entry
