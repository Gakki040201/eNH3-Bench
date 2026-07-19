from __future__ import annotations

import unittest

from enh3bench.cleanroom_schema import make_cleanroom_span_id


class CleanroomSpanIdentityTests(unittest.TestCase):
    def test_same_input_same_id(self) -> None:
        left = make_cleanroom_span_id("a" * 64, 10, 20, "performance_signal")
        self.assertEqual(left, make_cleanroom_span_id("a" * 64, 10, 20, "performance_signal"))

    def test_changed_offset_changes_id(self) -> None:
        self.assertNotEqual(
            make_cleanroom_span_id("a" * 64, 10, 20, "performance_signal"),
            make_cleanroom_span_id("a" * 64, 11, 20, "performance_signal"),
        )

    def test_same_text_in_different_documents_differs(self) -> None:
        self.assertNotEqual(
            make_cleanroom_span_id("a" * 64, 10, 20, "performance_signal"),
            make_cleanroom_span_id("b" * 64, 10, 20, "performance_signal"),
        )

    def test_run_name_is_not_an_input(self) -> None:
        value = make_cleanroom_span_id("a" * 64, 1, 2, "validation_signal")
        self.assertNotIn("run", value.casefold())

    def test_absolute_path_is_not_an_input(self) -> None:
        value = make_cleanroom_span_id("a" * 64, 1, 2, "validation_signal")
        self.assertNotIn(":", value)

    def test_candidate_kind_changes_id(self) -> None:
        self.assertNotEqual(
            make_cleanroom_span_id("a" * 64, 1, 2, "validation_signal"),
            make_cleanroom_span_id("a" * 64, 1, 2, "performance_signal"),
        )


if __name__ == "__main__":
    unittest.main()
