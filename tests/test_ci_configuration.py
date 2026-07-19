from __future__ import annotations

import unittest
from pathlib import Path


class CIConfigurationTests(unittest.TestCase):
    def test_ci_runs_unittest_and_gold_without_dangerous_capabilities(self) -> None:
        path = Path(".github/workflows/ci.yml")
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8").casefold()
        self.assertIn("python -m unittest discover", text)
        self.assertIn("check_gold_integrity.py", text)
        self.assertIn("report_gold_ci_availability.py", text)
        self.assertIn("if: always()", text)
        self.assertIn("--require-baseline", text)
        self.assertIn("hashfiles('data/gold/", text)
        self.assertIn('"3.10"', text)
        self.assertIn('"3.13"', text)
        for forbidden in ("api_key", "input_raw", "download", "contents: write", "git push", "secrets."):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
