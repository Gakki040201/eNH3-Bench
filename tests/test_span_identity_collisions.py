from __future__ import annotations

import unittest

from enh3bench.span_identity import attach_span_identity, build_stable_span_uid


class SpanIdentityCollisionTests(unittest.TestCase):
    def test_offsets_distinguish_repeated_text_and_preserve_ids(self) -> None:
        records = [
            {"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S001", "section_path": ["Results"], "source_text": "Same", "source_start_offset": 10, "source_end_offset": 14},
            {"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S002", "section_path": ["Results"], "source_text": "Same", "source_start_offset": 20, "source_end_offset": 24},
        ]
        attached = attach_span_identity(records)
        self.assertNotEqual(attached[0]["stable_span_uid"], attached[1]["stable_span_uid"])
        self.assertTrue(all(r["stable_span_uid_method"] == "offset_anchored" for r in attached))
        self.assertEqual([r["source_span_id"] for r in attached], ["P1_S001", "P1_S002"])

    def test_duplicate_offset_and_text_raises(self) -> None:
        base = {"paper_id": "P1", "document_id": "P1", "section_path": ["Results"], "source_text": "Same", "source_start_offset": 10, "source_end_offset": 14}
        with self.assertRaises(ValueError):
            attach_span_identity([{**base, "source_span_id": "P1_S001"}, {**base, "source_span_id": "P1_S002"}])

    def test_legacy_order_then_id_fallback_and_key_order_independence(self) -> None:
        ordered = attach_span_identity([{"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S007", "source_text": "Text"}])[0]
        fallback = attach_span_identity([{"paper_id": "P1", "document_id": "P1", "source_span_id": "legacy-x", "source_text": "Text"}])[0]
        self.assertEqual(ordered["stable_span_uid_method"], "legacy_order_anchored")
        self.assertEqual(fallback["stable_span_uid_method"], "legacy_id_fallback")
        self.assertEqual(build_stable_span_uid({"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Text"}), build_stable_span_uid({"source_text": "Text", "source_span_id": "P1_S001", "paper_id": "P1"}))


if __name__ == "__main__":
    unittest.main()
