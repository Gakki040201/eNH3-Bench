from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UltimateSmokeTests(unittest.TestCase):
    def test_unified_runner_creates_audit_stage_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "input_raw"
            markdown_dir = base / "input_markdown"
            input_dir.mkdir()
            (input_dir / "linrr.txt").write_text(
                "Li-mediated N2 reduction in THF produced NH3 at 10.5 nmol s-1 cm-2 "
                "with 62% FE, 15N2 isotope validation, and blank control.",
                encoding="utf-8",
            )
            (input_dir / "no3rr.md").write_text(
                "Nitrate reduction to ammonia using NO3- electrolyte reached 85% "
                "Faradaic efficiency and reported ammonia yield rate.",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_enh3_scholar.py"),
                    "--input-dir",
                    str(input_dir),
                    "--markdown-dir",
                    str(markdown_dir),
                    "--run-name",
                    "smoke",
                    "--top-n",
                    "4",
                    "--max-per-paper",
                    "2",
                    "--stop-at",
                    "audit",
                ],
                cwd=base,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((base / "data" / "candidates" / "candidate_spans.smoke.jsonl").exists())
            self.assertTrue((base / "data" / "drafts" / "draft_evidence.smoke.jsonl").exists())
            self.assertTrue((base / "data" / "drafts" / "field_grounding.smoke.jsonl").exists())
            self.assertTrue((base / "data" / "drafts" / "draft_feedback.smoke.jsonl").exists())
            self.assertTrue((base / "data" / "audit" / "audit_packet.smoke.md").exists())
            self.assertTrue((base / "data" / "audit" / "review_sheet.smoke.csv").exists())


if __name__ == "__main__":
    unittest.main()
