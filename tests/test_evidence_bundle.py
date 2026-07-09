from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.evidence_bundle import (
    build_evidence_bundle,
    build_evidence_bundles,
    export_evidence_bundles,
    load_records_from_ledgers,
)


class EvidenceBundleTests(unittest.TestCase):
    def test_build_evidence_bundle_preserves_raw_record_and_grounding(self) -> None:
        record = {
            "span_id": "S001",
            "paper_id": "P001",
            "document_id": "D001",
            "text": "N2 reduction produced NH3 with 15N2 validation and indophenol quantification.",
            "text_class": "primary_performance_with_validation",
            "recommended_ledger": "performance",
            "allow_field_extraction": True,
            "allow_gold": True,
            "faradaic_efficiency_percent": 55.0,
        }
        bundle = build_evidence_bundle(record)
        self.assertEqual(bundle["source_span_id"], "S001")
        self.assertEqual(bundle["doi"], "")
        self.assertEqual(bundle["grounding_status"], "explicit_source_text")
        self.assertEqual(bundle["raw_record"]["span_id"], "S001")
        self.assertEqual(bundle["extracted_fields"]["faradaic_efficiency_percent"], 55.0)

    def test_load_records_prefers_classified_spans(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            run_dir = base / "run1"
            run_dir.mkdir(parents=True)
            record = {"span_id": "S001", "paper_id": "P001", "source_text": "primary text"}
            (run_dir / "classified_spans.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

            records = load_records_from_ledgers("run1", base)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["run_name"], "run1")

    def test_export_evidence_bundles_writes_jsonl_and_csv(self) -> None:
        bundles = build_evidence_bundles(
            [
                {
                    "span_id": "S001",
                    "paper_id": "P001",
                    "source_text": "A sufficiently long grounded source span for export.",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_evidence_bundles(bundles, "run1", temp_dir)
            self.assertTrue(Path(outputs["jsonl"]).exists())
            self.assertTrue(Path(outputs["csv"]).exists())
            with Path(outputs["csv"]).open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["paper_id"], "P001")


if __name__ == "__main__":
    unittest.main()
