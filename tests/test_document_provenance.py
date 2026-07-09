from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.document_provenance import (
    attach_provenance_to_records,
    extract_provenance_from_docling_json,
    infer_provenance_for_record,
    load_docling_json,
    summarize_provenance,
)
from enh3bench.evidence_bundle import build_evidence_bundle


class DocumentProvenanceTests(unittest.TestCase):
    def test_extract_docling_like_items(self) -> None:
        data = {
            "document_id": "D001",
            "texts": [
                {"id": "b1", "label": "text", "text": "Results showed FE and NH3 yield.", "section": "Results", "page": 2},
                {"id": "t1", "label": "table", "text": "| Catalyst | FE |\n|---|---|\n| this work | 10 |", "page": 3},
            ],
        }
        records = extract_provenance_from_docling_json(data, paper_id="P001")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["provenance_type"], "results")
        self.assertEqual(records[1]["provenance_type"], "table")
        self.assertEqual(records[1]["page"], 3)

    def test_load_docling_json_handles_bad_or_good_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "doc.json"
            path.write_text(json.dumps({"texts": []}), encoding="utf-8")
            self.assertEqual(load_docling_json(path), {"texts": []})
            bad = Path(temp_dir) / "bad.json"
            bad.write_text("{", encoding="utf-8")
            self.assertEqual(load_docling_json(bad), {})

    def test_infer_and_attach_provenance_for_record(self) -> None:
        record = {
            "span_id": "S001",
            "paper_id": "P001",
            "source_section": "Results",
            "source_text": "The catalyst produced NH3 with FE and yield.",
        }
        provenance = infer_provenance_for_record(record)
        self.assertEqual(provenance["source_span_id"], "S001")
        self.assertEqual(provenance["provenance_type"], "results")
        attached = attach_provenance_to_records([record])
        self.assertEqual(attached[0]["provenance_type"], "results")

    def test_summary_counts(self) -> None:
        summary = summarize_provenance(
            [
                {"provenance_type": "results", "is_primary_admissible": True},
                {"provenance_type": "reference", "is_reject_or_low_trust": True},
            ]
        )
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["primary_admissible_count"], 1)
        self.assertEqual(summary["reject_or_low_trust_count"], 1)

    def test_evidence_bundle_from_old_record_infers_provenance(self) -> None:
        bundle = build_evidence_bundle(
            {
                "span_id": "S001",
                "paper_id": "P001",
                "source_section": "Results",
                "source_text": "The catalyst produced NH3 with 15N2 validation.",
            }
        )
        self.assertEqual(bundle["provenance_type"], "results")
        self.assertIn("provenance_signals", bundle)


if __name__ == "__main__":
    unittest.main()
