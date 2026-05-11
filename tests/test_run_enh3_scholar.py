from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Python314\python.exe")


class RunEnh3ScholarTests(unittest.TestCase):
    def test_cli_runs_to_audit_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_dir = base / "input_raw"
            markdown_dir = base / "input_markdown"
            input_dir.mkdir()
            (input_dir / "P001.txt").write_text(
                "Li-mediated N2 reduction produced NH3 at 10.5 nmol s-1 cm-2 "
                "with 62% FE and 15N2 isotope labeling plus blank control.",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(PYTHON),
                    str(ROOT / "scripts" / "run_enh3_scholar.py"),
                    "--input-dir",
                    str(input_dir),
                    "--markdown-dir",
                    str(markdown_dir),
                    "--run-name",
                    "test",
                    "--top-n",
                    "4",
                    "--max-per-paper",
                    "2",
                    "--stop-at",
                    "audit",
                ],
                cwd=base,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((base / "data" / "audit" / "audit_packet.test.md").exists())
            self.assertTrue((base / "data" / "audit" / "review_sheet.test.csv").exists())
            self.assertIn("Next human step", result.stdout)


if __name__ == "__main__":
    unittest.main()
