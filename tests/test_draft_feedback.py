from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.draft_feedback import generate_feedback  # noqa: E402


class DraftFeedbackTests(unittest.TestCase):
    def test_high_feedback_when_isotope_yes_lacks_15n(self) -> None:
        feedback = generate_feedback(
            {"source_span": "NH3 was produced.", "isotope_validation": "yes"},
            {"grounding": [{"field": "isotope_validation", "grounding_status": "inferred"}]},
        )
        self.assertTrue(any(item["severity"] == "high" for item in feedback))

    def test_reliability_a_without_isotope_yes_triggers_high(self) -> None:
        feedback = generate_feedback({"reliability_label": "A", "isotope_validation": "unclear"})
        self.assertTrue(any(item["field"] == "reliability_label" for item in feedback))

    def test_review_like_wording_triggers_evidence_type_warning(self) -> None:
        feedback = generate_feedback(
            {"source_span": "This review summarized results reported by prior literature.", "evidence_type": "primary_claim"}
        )
        self.assertTrue(any(item["field"] == "evidence_type" for item in feedback))

    def test_missing_nh3_yield_unit_triggers_feedback(self) -> None:
        feedback = generate_feedback({"nh3_yield_value": 10.0, "nh3_yield_unit": None})
        self.assertTrue(any(item["field"] == "nh3_yield_unit" for item in feedback))


if __name__ == "__main__":
    unittest.main()
