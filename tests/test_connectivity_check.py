import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add scripts directory to path so we can import connectivity_check
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import connectivity_check
from connectivity_check import TestContext, TestResult

class TestConnectivityCheck(unittest.TestCase):
    def setUp(self):
        self.ctx = TestContext(
            ip="127.0.0.1",
            gateway_port=8080,
            timeout=1,
            lmstudio_model="test-model",
            openrouter_model="test-or-model",
            kokoro_voice="af_bella",
            gateway_api_key="secret-key"
        )
        self.session = MagicMock()

    @patch("requests.Session")
    def test_lmstudio_chat_success(self, mock_session_cls):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
        self.session.post.return_value = mock_response

        result = connectivity_check.lmstudio_chat(self.session, self.ctx)
        
        self.assertTrue(result.ok)
        self.assertEqual(result.name, "Gateway → LM Studio chat")
        self.session.post.assert_called_once()
        args, kwargs = self.session.post.call_args
        self.assertIn("X-API-Key", kwargs["headers"])
        self.assertEqual(kwargs["headers"]["X-API-Key"], "secret-key")

    def test_lmstudio_chat_failure(self):
        # Setup mock exception
        self.session.post.side_effect = Exception("Connection refused")
        
        result = connectivity_check.lmstudio_chat(self.session, self.ctx)
        
        self.assertFalse(result.ok)
        self.assertIn("Connection refused", result.detail)

    def test_kokoro_tts_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "audio/mpeg"}
        self.session.post.return_value = mock_response

        result = connectivity_check.kokoro_tts(self.session, self.ctx)
        
        self.assertTrue(result.ok)
        self.assertIn("audio/mpeg", result.detail)

    def test_openrouter_models_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "model1"}]}
        self.session.get.return_value = mock_response

        result = connectivity_check.openrouter_models(self.session, self.ctx)

        self.assertTrue(result.ok)
        self.assertEqual(result.detail, "1 models listed")

    def test_headers_helper(self):
        headers = connectivity_check._headers("cls-key", {"Extra": "Value"})
        self.assertEqual(headers["X-API-Key"], "cls-key")
        self.assertEqual(headers["Extra"], "Value")

if __name__ == "__main__":
    unittest.main()
