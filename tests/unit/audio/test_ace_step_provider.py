from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from engine.audio.providers.ace_step import ACEStepProvider, local_music_provider, ACE_STEP_DIR, ACE_STEP_PYTHON


class TestACEStepProvider(unittest.TestCase):
    def test_init_and_paths(self):
        provider = ACEStepProvider("http://127.0.0.1:8001")
        self.assertEqual(provider.base_url, "http://127.0.0.1:8001")
        self.assertTrue(ACE_STEP_DIR.exists(), "ACE_STEP_DIR should exist in C:\\Tools\\ACE-Step-1.5")
        self.assertTrue(ACE_STEP_PYTHON.exists(), "ACE-Step Python executable must exist in .venv")

    def test_check_health_offline(self):
        provider = ACEStepProvider("http://127.0.0.1:9999")
        health = provider.check_health(timeout=0.1)
        self.assertFalse(health["available"])
        self.assertEqual(health["status"], "offline")

    def test_lumina_audio_director_integration(self):
        from lumina_audio_director.adapters.ace_step_adapter import ACEStepAdapter
        adapter = ACEStepAdapter()
        self.assertEqual(adapter.adapter_id, "acestep_15_turbo")
        self.assertEqual(adapter.adapter_name, "ACE-Step 1.5 Turbo")

    @patch("urllib.request.urlopen")
    def test_check_health_mock_online(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"code": 200, "data": {"status": "ok", "service": "ACE-Step API", "models_initialized": true, "loaded_model": "acestep-v15-turbo"}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        provider = ACEStepProvider("http://127.0.0.1:8001")
        health = provider.check_health(timeout=1.0)
        self.assertTrue(health["available"])
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["loaded_model"], "acestep-v15-turbo")


if __name__ == "__main__":
    unittest.main()
