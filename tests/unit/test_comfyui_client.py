import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.comfyui import ComfyUIClient, ComfyUIError


class ComfyUIClientTests(unittest.TestCase):
    def test_discovery_is_scoped_to_workflow_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "approved.json").write_text("{}", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "draft.json").write_text("{}", encoding="utf-8")
            client = ComfyUIClient(base_url="http://127.0.0.1:8188", workflow_dir=root)
            self.assertEqual(client.discover_workflows(), ["approved.json", "nested/draft.json"])

    def test_capabilities_fail_closed_when_server_is_unavailable(self):
        client = ComfyUIClient(base_url="http://127.0.0.1:1")
        result = client.capabilities()
        self.assertFalse(result["available"])
        self.assertTrue(result["errors"])

    def test_prompt_submission_requires_prompt_id(self):
        client = ComfyUIClient()
        client._request_json = lambda *args, **kwargs: {}
        with self.assertRaises(ComfyUIError):
            client.submit_prompt({"1": {"class_type": "CheckpointLoaderSimple"}})

    def test_malformed_or_remote_urls_fail_closed(self):
        with self.assertRaises(ComfyUIError):
            ComfyUIClient(base_url="http://[malformed")
        with self.assertRaises(ComfyUIError):
            ComfyUIClient(base_url="https://example.com")

    def test_history_rejects_path_like_prompt_ids(self):
        client = ComfyUIClient()
        with self.assertRaises(ValueError):
            client.history("../secrets")

    def test_remote_comfyui_requires_public_ip_literal(self):
        with patch.dict(
            "os.environ",
            {
                "PANELFLOW_COMFYUI_ALLOW_REMOTE": "true",
                "PANELFLOW_COMFYUI_ALLOWED_HOSTS": "example.com",
            },
            clear=False,
        ):
            with self.assertRaises(ComfyUIError):
                ComfyUIClient(base_url="https://example.com")

    def test_output_retrieval_rejects_absolute_subfolder_and_unknown_type(self):
        client = ComfyUIClient()
        with self.assertRaises(ValueError):
            client.download_output("image.png", "/outside")
        with self.assertRaises(ValueError):
            client.download_output("image.png", folder_type="secret")

    def test_output_retrieval_rejects_drive_relative_subfolder_before_network(self):
        client = ComfyUIClient()
        with patch("engine.comfyui.client._NO_REDIRECT_OPENER.open") as open_request:
            with self.assertRaises(ValueError):
                client.download_output("image.png", "C:secret")
            open_request.assert_not_called()

    def test_output_retrieval_rejects_input_and_temp_history_artifacts(self):
        client = ComfyUIClient()
        for folder_type in ("input", "temp"):
            with self.subTest(folder_type=folder_type), self.assertRaises(ValueError):
                client.download_output("image.png", folder_type=folder_type)

    def test_discovery_omits_symlinked_files_and_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "workflow"
            root.mkdir()
            outside = base / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            try:
                (root / "outside.json").symlink_to(outside)
                (base / "linked_root").symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            client = ComfyUIClient(workflow_dir=root)
            self.assertEqual(client.discover_workflows(), [])
            self.assertEqual(ComfyUIClient(workflow_dir=base / "linked_root").discover_workflows(), [])

    def test_model_discovery_omits_linked_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            workflow = base / "workflow"
            workflow.mkdir()
            category = base / "models" / "checkpoints"
            category.mkdir(parents=True)
            linked = category / "linked.safetensors"
            linked.write_bytes(b"model")
            client = ComfyUIClient(workflow_dir=workflow)
            original = type(linked).is_symlink
            with patch.object(type(linked), "is_symlink", lambda self: self == linked or original(self)):
                self.assertEqual(client.discover_models().get("checkpoints"), [])


if __name__ == "__main__":
    unittest.main()
