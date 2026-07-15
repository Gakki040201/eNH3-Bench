from __future__ import annotations

import copy
import unittest

from enh3bench.span_context import (
    build_document_span_index,
    get_adjacent_spans,
    get_next_spans,
    get_previous_spans,
    get_same_section_spans,
)


class SpanContextTests(unittest.TestCase):
    def test_adjacent_and_same_section_queries_are_ordered(self) -> None:
        index = build_document_span_index([
            _record("P1_S003", "Methods", "third"),
            _record("P1_S001", "Results", "first"),
            _record("P1_S002", "Results", "second"),
        ])
        self.assertEqual([item["span_id"] for item in get_previous_spans(index, "P1_S002")], ["P1_S001"])
        self.assertEqual([item["span_id"] for item in get_next_spans(index, "P1_S002")], ["P1_S003"])
        self.assertEqual([item["span_id"] for item in get_adjacent_spans(index, "P1_S002")], ["P1_S001", "P1_S003"])
        self.assertEqual([item["span_id"] for item in get_same_section_spans(index, "P1_S002")], ["P1_S001"])

    def test_explicit_order_precedes_legacy_and_fallback_warns(self) -> None:
        index = build_document_span_index([
            {**_record("nonstandard", "Results", "explicit"), "span_order": 0},
            _record("P1_S001", "Results", "parsed"),
            _record("fallback", "Results", "fallback"),
        ])
        ordered = index.paper_records["P1"]
        self.assertEqual([record["legacy_span_id"] for record in ordered], ["nonstandard", "P1_S001", "fallback"])
        self.assertTrue(any("span_order_fallback_to_input:fallback" in warning for warning in index.warnings))

    def test_context_only_flag_and_no_input_mutation(self) -> None:
        records = [_record("P1_S001", "References", "citation", provenance="reference", text_class="reference_list"), _record("P1_S002", "Results", "target")]
        before = copy.deepcopy(records)
        index = build_document_span_index(records)
        previous = get_previous_spans(index, "P1_S002")[0]
        self.assertTrue(previous["context_only"])
        self.assertEqual(records, before)

    def test_missing_target_and_duplicate_id_fail(self) -> None:
        index = build_document_span_index([_record("P1_S001", "Results", "one")])
        with self.assertRaises(KeyError):
            get_next_spans(index, "missing")
        with self.assertRaises(ValueError):
            build_document_span_index([_record("P1_S001", "A", "one"), _record("P1_S001", "B", "two")])


def _record(span_id: str, section: str, text: str, provenance: str = "body", text_class: str = "primary_performance") -> dict[str, object]:
    return {"paper_id": "P1", "source_span_id": span_id, "section_path": [section], "section_heading": section, "source_text": text, "provenance_type": provenance, "text_class": text_class}


if __name__ == "__main__":
    unittest.main()
