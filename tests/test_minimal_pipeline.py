from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.minimal_pipeline import run_minimal_review_pipeline  # noqa: E402


class MinimalPipelineTests(unittest.TestCase):
    def test_minimal_pipeline_creates_expected_files(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_markdown = base / "input_markdown"
            input_markdown.mkdir()
            (input_markdown / "P007.md").write_text(
                "Li-mediated N2 reduction in THF produced NH3 at 10.5 nmol s-1 cm-2 "
                "with 62% Faradaic efficiency and 15N2 isotope labeling.",
                encoding="utf-8",
            )
            try:
                os.chdir(base)
                manifest = run_minimal_review_pipeline(
                    input_markdown_dir=input_markdown,
                    run_name="test",
                    max_spans_per_document=6,
                )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(manifest["document_count"], 1)
            self.assertEqual(manifest["candidate_span_count"], 1)
            self.assertEqual(manifest["draft_evidence_count"], 1)

            candidate_path = base / "data" / "candidates" / "candidate_spans.test.jsonl"
            draft_path = base / "data" / "drafts" / "draft_evidence.test.jsonl"
            audit_path = base / "data" / "audit" / "audit_packet.test.md"
            review_path = base / "data" / "audit" / "review_sheet.test.csv"
            instructions_path = base / "data" / "audit" / "HUMAN_VERIFICATION_INSTRUCTIONS.md"
            manifest_path = base / "data" / "reports" / "workflow_manifest.test.json"

            for path in [
                candidate_path,
                draft_path,
                audit_path,
                review_path,
                instructions_path,
                manifest_path,
            ]:
                self.assertTrue(path.exists(), path)

            draft = json.loads(draft_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("Li-mediated N2 reduction", draft["source_span"])
            self.assertIn("Open data/audit/audit_packet.test.md", manifest["next_human_step"])

            with review_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["paper_id"], "P007")
            self.assertIn("reliability_label", rows[0]["fields_to_check"])


if __name__ == "__main__":
    unittest.main()
