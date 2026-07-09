from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from enh3bench.llm_clients import MockLLMClient, OpenAICompatibleClient, sanitize_model_name_for_path
from enh3bench.llm_clients.openai_compatible import normalize_chat_completions_endpoint


class LLMClientTests(unittest.TestCase):
    def test_endpoint_normalization(self) -> None:
        self.assertEqual(
            normalize_chat_completions_endpoint("https://api.llm.ustc.edu.cn"),
            "https://api.llm.ustc.edu.cn/v1/chat/completions",
        )
        self.assertEqual(
            normalize_chat_completions_endpoint("https://api.llm.ustc.edu.cn/v1"),
            "https://api.llm.ustc.edu.cn/v1/chat/completions",
        )
        self.assertEqual(
            normalize_chat_completions_endpoint("https://api.llm.ustc.edu.cn/v1/chat/completions"),
            "https://api.llm.ustc.edu.cn/v1/chat/completions",
        )

    def test_missing_env_handling(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            client = OpenAICompatibleClient()
            available, message = client.verify_available()
        self.assertFalse(available)
        self.assertIn("missing API key", message)

    def test_env_resolution(self) -> None:
        with patch.dict(
            os.environ,
            {
                "USTC_API_KEY": "secret",
                "USTC_BASE_URL": "https://api.llm.ustc.edu.cn",
                "USTC_MODEL": "ustc-model",
            },
            clear=True,
        ):
            client = OpenAICompatibleClient()
            available, _ = client.verify_available()
        self.assertTrue(available)
        self.assertEqual(client.endpoint, "https://api.llm.ustc.edu.cn/v1/chat/completions")
        self.assertEqual(client.model, "ustc-model")

    def test_path_sanitization(self) -> None:
        self.assertEqual(sanitize_model_name_for_path('ustc/model:alpha beta?'), "ustc_model_alpha_beta")
        self.assertEqual(sanitize_model_name_for_path(""), "model")

    def test_mock_client_returns_strict_json(self) -> None:
        prompt = [
            {"role": "system", "content": "test"},
            {
                "role": "user",
                "content": (
                    "Record to verify:\n"
                    '{"source_text":"15N2 flow cell FE for NH3","provenance_type":"body","text_class":"primary_performance"}\n'
                    "Return strict JSON with exactly these top-level keys:\n{}"
                ),
            },
        ]
        response = MockLLMClient().chat(prompt, model="mock")
        parsed = json.loads(response)
        self.assertEqual(parsed["maximum_supported_boundary"], "reactor_legibility")
        self.assertIn("field_support", parsed)


if __name__ == "__main__":
    unittest.main()
