from __future__ import annotations

import unittest

from enh3bench.calibration_sampling import (
    matching_span_strata,
    sample_links,
    sample_papers,
    sample_spans,
    sampling_hash,
)


def span(index: int, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "cleanroom_span_id": f"CR15_{index:020X}", "paper_id": f"P{index // 5}",
        "semantic_claim_type": "mechanism_claim", "claim_ownership": "unclear",
        "document_genre": "primary_research", "document_reaction_family": "unclear",
        "effective_reaction_family": "unclear", "primary_semantic_eligibility": False,
        "ammonia_quantification_signal": False, "gas_purification_trap_signal": False,
        "validation_gate_decisions": {}, "needs_review": True, "hard_gate_failures": ["x"],
    }
    value.update(overrides)
    return value


class CalibrationSamplingV016Tests(unittest.TestCase):
    def test_sampling_hash_is_stable(self) -> None:
        self.assertEqual(sampling_hash(16, "CR15_X"), sampling_hash(16, "CR15_X"))
        self.assertNotEqual(sampling_hash(16, "CR15_X"), sampling_hash(17, "CR15_X"))

    def test_matching_strata_uses_structured_fields(self) -> None:
        record = span(1, semantic_claim_type="validation_claim", document_genre="review")
        self.assertIn("validation", matching_span_strata(record))
        self.assertIn("review_perspective", matching_span_strata(record))

    def test_exact_span_sample_size_and_uniqueness(self) -> None:
        selected, _ = sample_spans([span(index) for index in range(80)], 30, 16)
        self.assertEqual(len(selected), 30)
        self.assertEqual(len({item["cleanroom_span_id"] for item in selected}), 30)

    def test_stratum_shortage_is_explicit(self) -> None:
        _, coverage = sample_spans([span(index) for index in range(80)], 30, 16)
        self.assertGreater(coverage["primary_performance"]["shortage"], 0)
        self.assertGreater(coverage["high_risk_reservoir"]["selected"], 0)

    def test_deterministic_quota_fill(self) -> None:
        records = [span(index) for index in range(80)]
        left, _ = sample_spans(records, 30, 16)
        right, _ = sample_spans(list(reversed(records)), 30, 16)
        self.assertEqual([item["cleanroom_span_id"] for item in left], [item["cleanroom_span_id"] for item in right])

    def test_total_shortage_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "insufficient semantic spans"):
            sample_spans([span(index) for index in range(5)], 6, 16)

    def test_duplicate_source_ids_fail_closed(self) -> None:
        records = [span(index) for index in range(40)]
        records.append(dict(records[0]))
        with self.assertRaises(AssertionError):
            sample_spans(records, 41, 16)

    def test_link_shortage_includes_all_valid_links(self) -> None:
        spans = [span(1, source_start_offset=0, source_node_id="N1"), span(2, source_start_offset=10, source_node_id="N2")]
        link = {
            "evidence_link_id": "CRL15_00000000000000000001", "paper_id": "P0",
            "target_cleanroom_span_id": spans[0]["cleanroom_span_id"],
            "evidence_cleanroom_span_id": spans[1]["cleanroom_span_id"],
            "link_roles": ["validation_support"], "source_eligibility": "primary_admissible",
        }
        selected, coverage = sample_links([link], spans, 3, 16)
        self.assertEqual(len(selected), 1)
        self.assertEqual(coverage["shortage"], 2)


if __name__ == "__main__":
    unittest.main()
