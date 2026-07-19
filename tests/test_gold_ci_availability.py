from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.report_gold_ci_availability import report_gold_ci_availability


ROOT = Path(__file__).resolve().parents[1]


class GoldCiAvailabilityTests(unittest.TestCase):
    def test_missing_gold_is_explicit_and_non_failing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = report_gold_ci_availability("fixture", gold_root=temp)
            self.assertEqual(result["status"], "local_authoritative_gold_not_committed")
            self.assertFalse(result["exact_integrity_check_available"])

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "report_gold_ci_availability.py"),
                    "--run-name", "fixture", "--gold-root", temp,
                ],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertIn("local_authoritative_gold_not_committed", completed.stdout)

    def test_both_local_gold_files_report_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp) / "fixture"
            run_dir.mkdir()
            run_dir.joinpath("human_gold_claim_rights.jsonl").write_text("{}\n", encoding="utf-8")
            run_dir.joinpath("human_gold_claim_rights.csv").write_text("source_span_id\n", encoding="utf-8")
            result = report_gold_ci_availability("fixture", gold_root=temp)
            self.assertEqual(result["status"], "available")
            self.assertTrue(result["exact_integrity_check_available"])


if __name__ == "__main__":
    unittest.main()
