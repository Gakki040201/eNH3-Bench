from __future__ import annotations

from collections import Counter
import unittest

from enh3bench.e2e_eval_schema import ANCHOR_TYPE_QUOTAS, make_anchor_id
from enh3bench.e2e_risk_routing import build_risk_ledger
from enh3bench.selective_calibration import make_anchor_review_rows, select_anchors
from tests.selective_eval_test_helpers import synthetic_frames


class SelectiveCalibrationV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = synthetic_frames()
        cls.ledger = build_risk_ledger(cls.frames)
        cls.anchors = select_anchors(cls.frames, cls.ledger, seed=16)

    def test_stable_anchor_id(self) -> None:
        self.assertEqual(make_anchor_id("span", "CC16S_example"), make_anchor_id("span", "CC16S_example"))
        self.assertTrue(make_anchor_id("span", "CC16S_example").startswith("SC16A_"))

    def test_exact_anchor_selection(self) -> None:
        self.assertEqual(len(self.anchors), 24)
        self.assertEqual(len({row["source_calibration_item_id"] for row in self.anchors}), 24)

    def test_anchor_type_quotas(self) -> None:
        self.assertEqual(Counter(row["anchor_type"] for row in self.anchors), Counter(ANCHOR_TYPE_QUOTAS))

    def test_required_span_categories_and_sentinel(self) -> None:
        counts = Counter(row["selection_category"] for row in self.anchors if row["anchor_type"] == "span")
        self.assertEqual(counts["primary_performance"], 2)
        self.assertEqual(counts["quantification"], 2)
        self.assertEqual(counts["validation"], 2)
        for category in (
            "external_cited_claim", "off_target", "trap_only", "unclear_mixed_family",
            "high_risk_reservoir", "random_sentinel",
        ):
            self.assertEqual(counts[category], 1)

    def test_selection_is_deterministic(self) -> None:
        repeated = select_anchors(self.frames, self.ledger, seed=16)
        self.assertEqual(self.anchors, repeated)

    def test_only_selected_anchors_get_double_review(self) -> None:
        reviews = make_anchor_review_rows(self.anchors)
        self.assertEqual(len(reviews), 48)
        self.assertEqual(set(row["reviewer_id"] for row in reviews), {"R1", "R2"})
        self.assertTrue(all(not row["review_status"] for row in reviews))
        self.assertTrue(all(not value for row in reviews for key, value in row.items() if key.startswith("human_")))


if __name__ == "__main__":
    unittest.main()
