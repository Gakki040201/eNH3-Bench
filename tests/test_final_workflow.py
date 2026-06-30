from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from enh3bench.final_workflow import (
    check_final_output_status,
    render_final_output_check,
    run_final_triage_workflow,
)


class FinalWorkflowTests(unittest.TestCase):
    def test_final_workflow_creates_core_outputs(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_raw = base / "input_raw"
            markdown_dir = base / "input_markdown"
            input_raw.mkdir()
            (input_raw / "P001.txt").write_text(
                "Li-mediated N2 reduction in a flow cell produced NH3 at 10.5 nmol s-1 cm-2 "
                "with 62% FE at 20 mA cm-2, 15N2 isotope labeling, blank control, "
                "NOx screening, contamination control, NMR detection, and 24 h stability.",
                encoding="utf-8",
            )
            try:
                os.chdir(base)
                manifest = run_final_triage_workflow(
                    input_dir=input_raw,
                    markdown_dir=markdown_dir,
                    run_name="test",
                    converter="basic",
                    top_n=5,
                    max_per_paper=3,
                    force_reconvert=True,
                )
                checks = check_final_output_status("test")
            finally:
                os.chdir(original_cwd)

            self.assertEqual(manifest["classified_span_count"], 1)
            self.assertEqual(manifest["performance_records_scored"], 1)
            self.assertTrue((base / "data" / "ledgers" / "test" / "classified_spans.jsonl").exists())
            self.assertTrue((base / "data" / "reports" / "experiment_triage_report.test.md").exists())
            self.assertFalse(any(item["required"] and not item["exists"] for item in checks))
            self.assertIn("All required outputs are present", render_final_output_check(checks))


if __name__ == "__main__":
    unittest.main()
