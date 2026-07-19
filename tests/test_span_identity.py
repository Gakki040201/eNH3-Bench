from __future__ import annotations

import unittest

from enh3bench.span_identity import (
    attach_span_identity,
    build_stable_span_uid,
    normalize_span_text,
    parse_legacy_span_order,
)


class SpanIdentityTests(unittest.TestCase):
    def test_uid_is_deterministic_and_key_order_independent(self) -> None:
        first = {"paper_id": "P1", "section_path": ["Results"], "source_text": "FE 20%"}
        second = {"source_text": "FE 20%", "section_path": ["Results"], "paper_id": "P1"}
        self.assertEqual(build_stable_span_uid(first), build_stable_span_uid(second))

    def test_whitespace_normalization_preserves_uid(self) -> None:
        self.assertEqual(normalize_span_text(" FE\n 20%\t"), "FE 20%")
        self.assertEqual(
            build_stable_span_uid({"paper_id": "P1", "section_path": "Results", "source_text": "FE\n 20%"}),
            build_stable_span_uid({"paper_id": "P1", "section_path": " results ", "source_text": " FE  20% "}),
        )

    def test_different_papers_have_different_uid(self) -> None:
        base = {"section_path": "Results", "source_text": "Same text"}
        self.assertNotEqual(build_stable_span_uid({**base, "paper_id": "P1"}), build_stable_span_uid({**base, "paper_id": "P2"}))

    def test_legacy_order_parse_and_safe_failure(self) -> None:
        self.assertEqual(parse_legacy_span_order("Paper_S007"), 7)
        self.assertIsNone(parse_legacy_span_order("Paper-span-seven"))

    def test_attach_preserves_legacy_id_and_warns_on_unparseable(self) -> None:
        original = {"paper_id": "P1", "source_span_id": "legacy-id", "source_text": "Text"}
        attached = attach_span_identity([original])[0]
        self.assertEqual(original["source_span_id"], "legacy-id")
        self.assertEqual(attached["source_span_id"], "legacy-id")
        self.assertIsNone(attached["span_order"])
        self.assertIn("legacy_span_order_unparseable", attached["span_identity_warnings"])


if __name__ == "__main__":
    unittest.main()
