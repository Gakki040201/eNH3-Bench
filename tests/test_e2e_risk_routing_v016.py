from __future__ import annotations

import unittest
from copy import deepcopy

from enh3bench.e2e_case_generation import generate_cases
from enh3bench.e2e_risk_routing import build_risk_ledger, risk_tier, routes_for_tier, score_item
from tests.selective_eval_test_helpers import synthetic_frames


class E2ERiskRoutingV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = synthetic_frames()

    def test_full_deterministic_risk_ledger(self) -> None:
        first = build_risk_ledger(self.frames)
        second = build_risk_ledger(self.frames)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 520)

    def test_risk_explanation_is_traceable(self) -> None:
        scored = score_item("span", self.frames["span"][0])
        self.assertIsInstance(scored["risk_reasons"], list)
        required = {"code", "raw_weight", "weight", "correlation_group", "correlation_group_cap", "detail"}
        self.assertTrue(all(required == set(reason) for reason in scored["risk_reasons"]))
        self.assertEqual(scored["risk_score"], min(100, sum(reason["weight"] for reason in scored["risk_reasons"])))

    def test_tier_boundaries(self) -> None:
        self.assertEqual([risk_tier(value) for value in (0, 19, 20, 39, 40, 69, 70, 100)], ["T0", "T0", "T1", "T1", "T2", "T2", "T3", "T3"])

    def test_tier_routes(self) -> None:
        self.assertEqual(routes_for_tier("T0")[0], "auto_validate_only")
        self.assertEqual(routes_for_tier("T1")[0], "final_output_review")
        self.assertEqual(routes_for_tier("T2")[0], "intermediate_anchor_and_final_review")
        self.assertEqual(routes_for_tier("T3")[0], "abstain_then_review")

    def test_t3_does_not_imply_abstention(self) -> None:
        ledger = build_risk_ledger(self.frames)
        cases = generate_cases(self.frames, ledger, source_manifest_sha256="a" * 64, seed=16)
        self.assertTrue(any(
            case["automatic_case_risk_tier"] == "T3" and not case["abstention_expected"]
            for case in cases
        ))

    def test_correlated_span_risk_is_capped(self) -> None:
        row = deepcopy(self.frames["span"][0])
        row.update({
            "needs_review": True,
            "primary_semantic_eligibility": False,
            "hard_gate_failures": ["same_upstream_fact", "derived_gate"],
            "semantic_confidence": "high",
            "effective_reaction_family": "enrr",
            "claim_ownership": "target_authors",
            "assigned_primary_stratum": "primary_performance",
            "selection_stratum": "primary_performance",
            "all_matching_strata": [],
            "semantic_claim_type": "context_claim",
            "previous_context_excerpt": "context",
            "next_context_excerpt": "context",
        })
        scored = score_item("span", row)
        eligibility = [reason for reason in scored["risk_reasons"] if reason["correlation_group"] == "span_eligibility"]
        self.assertGreater(sum(reason["raw_weight"] for reason in eligibility), 28)
        self.assertEqual(sum(reason["weight"] for reason in eligibility), 28)
        self.assertNotEqual(scored["risk_tier"], "T3")

    def test_strong_structured_conflict_triggers_t3(self) -> None:
        row = deepcopy(self.frames["span"][0])
        row.update({
            "needs_review": False, "semantic_confidence": "high",
            "effective_reaction_family": "enrr", "claim_ownership": "target_authors",
            "assigned_primary_stratum": "structured_text_conflict",
            "selection_stratum": "structured_text_conflict", "primary_semantic_eligibility": True,
            "all_matching_strata": [], "semantic_claim_type": "context_claim",
            "hard_gate_failures": [], "previous_context_excerpt": "context", "next_context_excerpt": "context",
        })
        self.assertEqual(score_item("span", row)["risk_tier"], "T3")

    def test_scores_are_not_probabilities(self) -> None:
        scored = score_item("paper", self.frames["paper"][0])
        self.assertIsInstance(scored["risk_score"], int)
        self.assertLessEqual(scored["risk_score"], 100)


if __name__ == "__main__":
    unittest.main()
