from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from enh3bench.source_ledger import attach_source_coordinates_to_spans, build_ordered_source_ledger
from enh3bench.span_identity import attach_span_identity


class SpanSourceCoordinateAttachmentTests(unittest.TestCase):
    def test_verified_mismatch_multiple_and_identity_methods(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text("# Results\n\nUnique evidence.\n\nRepeated.\n\nRepeated.", encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            body = ledger.documents_by_id["P1"]["full_body_text"]
            start = body.index("Unique evidence.")
            records = [
                {"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S001", "source_text": "Unique evidence.", "source_start_offset": start, "source_end_offset": start + 16},
                {"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S002", "source_text": "Unique evidence.", "source_start_offset": 0, "source_end_offset": 5},
                {"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S003", "source_text": "Repeated."},
            ]
            before = copy.deepcopy(records)
            attached = attach_source_coordinates_to_spans(records, ledger)
            self.assertEqual(attached[0]["source_mapping_method"], "explicit_verified")
            self.assertEqual(attached[0]["source_mapping_confidence"], "high")
            self.assertTrue(attached[0]["offset_text_match"])
            self.assertNotEqual(attached[1]["source_mapping_confidence"], "high")
            self.assertIn("offset_text_mismatch", attached[1]["source_mapping_warnings"])
            self.assertEqual(attached[2]["source_mapping_method"], "unresolved")
            self.assertIn("multiple_exact_matches", attached[2]["source_mapping_warnings"])
            identified = attach_span_identity(attached[:2])
            self.assertEqual(identified[0]["stable_span_uid_method"], "offset_anchored_verified")
            self.assertEqual(identified[1]["stable_span_uid_method"], "legacy_order_anchored")
            self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
