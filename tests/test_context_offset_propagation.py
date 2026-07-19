from __future__ import annotations

import copy
import unittest

from enh3bench.context_packet import merge_context_sources


class ContextOffsetPropagationTests(unittest.TestCase):
    def test_precedence_and_none_preservation_without_mutation(self) -> None:
        bundle = {
            "paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Text",
            "source_start_offset": 4,
            "raw_record": {"document_id": "P1", "source_start_offset": 10, "source_end_offset": 20, "section_level": 2},
        }
        provenance = [{"source_span_id": "P1_S001", "source_start_offset": 30, "source_end_offset": 40, "section_type": "results"}]
        before = copy.deepcopy(bundle)
        record = merge_context_sources([bundle], [], [], provenance)[0]
        self.assertEqual(record["source_start_offset"], 10)
        self.assertEqual(record["source_end_offset"], 20)
        self.assertIsNone(record["section_type"])
        self.assertEqual(record["location_source"], "raw_record")
        self.assertEqual(record["location_sources"]["source_offset_pair"], "raw_record")
        self.assertIsNone(record["section_start_offset"])
        self.assertEqual(bundle, before)

    def test_provenance_fallback_and_unknown_offset_is_not_zero(self) -> None:
        record = merge_context_sources(
            [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Text"}], [], [],
            [{"source_span_id": "P1_S001", "document_id": "P1", "source_start_offset": 8, "source_end_offset": 12}],
        )[0]
        self.assertEqual((record["source_start_offset"], record["source_end_offset"]), (8, 12))
        self.assertEqual(record["location_source"], "provenance")
        self.assertIsNone(record["section_start_offset"])


if __name__ == "__main__":
    unittest.main()
