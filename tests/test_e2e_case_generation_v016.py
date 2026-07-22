from __future__ import annotations

from collections import Counter, defaultdict
import unittest

from enh3bench.e2e_case_generation import (
    EVALUATOR_ONLY_CASE_FIELDS,
    GENERATION_BATCH_FIELDS,
    assess_case_answerability,
    generate_cases,
    make_api_generation_batch,
    make_api_output_templates,
    make_e2e_human_review_rows,
    make_machine_judgment_templates,
)
from enh3bench.e2e_eval_schema import CASE_TYPE_QUOTAS
from enh3bench.e2e_risk_routing import build_risk_ledger
from tests.selective_eval_test_helpers import synthetic_frames


class E2ECaseGenerationV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = synthetic_frames()
        cls.ledger = build_risk_ledger(cls.frames)
        cls.cases = generate_cases(cls.frames, cls.ledger, source_manifest_sha256="a" * 64, seed=16)

    def test_exact_case_count_and_unique_papers(self) -> None:
        self.assertEqual(len(self.cases), 48)
        self.assertEqual(len({row["paper_id"] for row in self.cases}), 48)

    def test_case_type_quotas(self) -> None:
        self.assertEqual(Counter(row["case_type"] for row in self.cases), Counter(CASE_TYPE_QUOTAS))

    def test_exact_development_holdout_split(self) -> None:
        self.assertEqual(Counter(row["split"] for row in self.cases), {"development": 36, "holdout": 12})

    def test_no_split_leakage(self) -> None:
        development = {row["paper_id"] for row in self.cases if row["split"] == "development"}
        holdout = {row["paper_id"] for row in self.cases if row["split"] == "holdout"}
        self.assertFalse(development & holdout)

    def test_bounded_context(self) -> None:
        self.assertTrue(all(len(item["excerpt"]) <= 700 for case in self.cases for item in case["bounded_source_context"]))
        self.assertTrue(all(len(case["bounded_source_context"]) <= 6 for case in self.cases))

    def test_citation_allowlist_matches_context(self) -> None:
        for case in self.cases:
            spans = {item["source_span_id"] for item in case["bounded_source_context"] if item["source_span_id"]}
            links = {item["evidence_link_id"] for item in case["bounded_source_context"] if item["evidence_link_id"]}
            self.assertEqual(set(case["allowed_source_span_ids"]), spans)
            self.assertEqual(set(case["allowed_evidence_link_ids"]), links)

    def test_no_cross_paper_context(self) -> None:
        span_papers = {}
        for row in self.frames["span"]:
            span_papers[row["cleanroom_span_id"]] = row["paper_id"]
        for row in self.frames["link"]:
            span_papers[row["target_span_id"]] = row["paper_id"]
            span_papers[row["evidence_span_id"]] = row["paper_id"]
        for case in self.cases:
            self.assertTrue(all(span_papers[span_id] == case["paper_id"] for span_id in case["allowed_source_span_ids"]))

    def test_blank_api_outputs(self) -> None:
        outputs = make_api_output_templates(self.cases)
        self.assertEqual(len(outputs), 48)
        self.assertTrue(all(row["generation_status"] == "pending" and not row["answer_text"] for row in outputs))

    def test_blank_machine_judgments(self) -> None:
        judgments = make_machine_judgment_templates(self.cases)
        self.assertEqual(len(judgments), 96)
        self.assertTrue(all(not row["judge_id"] and row["judgment_status"] == "pending" for row in judgments))

    def test_two_reviewer_blank_rows(self) -> None:
        reviews = make_e2e_human_review_rows(self.cases)
        self.assertEqual(len(reviews), 96)
        by_case = defaultdict(set)
        for row in reviews:
            by_case[row["case_id"]].add(row["reviewer_id"])
            self.assertFalse(row["review_status"])
            self.assertTrue(all(not value for key, value in row.items() if key.startswith("human_") and key != "human_review_id"))
        self.assertTrue(all(reviewers == {"R1", "R2"} for reviewers in by_case.values()))

    def test_generation_batch_performs_no_network_call(self) -> None:
        batch = make_api_generation_batch(self.cases)
        self.assertTrue(all(row["network_call_performed"] is False for row in batch))
        self.assertTrue(all(set(row) == GENERATION_BATCH_FIELDS for row in batch))
        self.assertTrue(all(not (set(row) & EVALUATOR_ONLY_CASE_FIELDS) for row in batch))

    def test_case_frame_retains_evaluator_metadata(self) -> None:
        required = {
            "automatic_case_risk_score", "automatic_case_risk_tier",
            "automatic_case_risk_reasons", "automatic_signal_stratum",
            "answerability_status", "answerability_reasons", "abstention_expected", "split",
        }
        self.assertTrue(all(required.issubset(case) for case in self.cases))

    def test_case_answerability_is_explicit_and_recomputable(self) -> None:
        by_paper = defaultdict(lambda: defaultdict(list))
        for item_type, rows in self.frames.items():
            for row in rows:
                by_paper[row["paper_id"]][item_type].append(row)
        for case in self.cases:
            status, reasons = assess_case_answerability(
                by_paper[case["paper_id"]], case["case_type"], case["bounded_source_context"]
            )
            self.assertEqual((status, reasons), (case["answerability_status"], case["answerability_reasons"]))

    def test_each_case_type_has_non_abstention_coverage(self) -> None:
        for case_type in CASE_TYPE_QUOTAS:
            subset = [row for row in self.cases if row["case_type"] == case_type]
            self.assertTrue(any(row["answerability_status"] in {"answerable", "partially_answerable"} for row in subset))
            self.assertFalse(all(row["abstention_expected"] for row in subset))

    def test_missing_reactor_evidence_is_insufficient(self) -> None:
        status, reasons = assess_case_answerability(
            {"span": [], "paper": [{}], "document": [{}], "link": []},
            "reactor_process_extraction",
            [{"context_role": "document_front_matter", "excerpt": "A paper abstract."}],
        )
        self.assertEqual(status, "insufficient_evidence")
        self.assertIn("no_reactor_process_evidence_in_bounded_context", reasons)

    def test_off_target_scope_remains_answerable(self) -> None:
        status, _ = assess_case_answerability(
            {"document": [{"document_reaction_family": "linrr"}]},
            "paper_scope_classification",
            [{"context_role": "document_front_matter", "excerpt": "Lithium-mediated nitrogen reduction."}],
        )
        self.assertEqual(status, "answerable")

    def test_insufficient_primary_support_can_be_answered_negatively(self) -> None:
        group = {"span": [{
            "cleanroom_span_id": "S1", "semantic_claim_type": "performance_result_claim",
            "primary_semantic_eligibility": False,
        }]}
        status, reasons = assess_case_answerability(
            group, "primary_evidence_sufficiency",
            [{"context_role": "sampled_semantic_span", "source_span_id": "S1", "excerpt": "A performance claim."}],
        )
        self.assertEqual(status, "answerable")
        self.assertIn("negative_primary_sufficiency_assessment_possible", reasons)

    def test_incomplete_quantification_can_be_partially_answered(self) -> None:
        group = {
            "paper": [{"has_quantification_evidence": False}],
            "span": [{"cleanroom_span_id": "S2", "semantic_claim_type": "ammonia_quantification_claim"}],
        }
        status, _ = assess_case_answerability(
            group, "ammonia_quantification_assessment",
            [{"context_role": "sampled_semantic_span", "source_span_id": "S2", "excerpt": "Calibration was incomplete."}],
        )
        self.assertEqual(status, "partially_answerable")

    def test_reported_reactor_parameters_are_partially_answerable(self) -> None:
        group = {"span": [{"cleanroom_span_id": "S3", "semantic_claim_type": "reactor_claim"}]}
        status, reasons = assess_case_answerability(
            group, "reactor_process_extraction",
            [{"context_role": "sampled_semantic_span", "source_span_id": "S3", "excerpt": "Flow was 5 mL min-1."}],
        )
        self.assertEqual(status, "partially_answerable")
        self.assertIn("unreported_parameters_must_remain_missing", reasons)

    def test_empty_bounded_context_is_insufficient(self) -> None:
        status, reasons = assess_case_answerability({}, "reaction_family_identification", [])
        self.assertEqual(status, "insufficient_evidence")
        self.assertEqual(reasons, ["bounded_context_empty"])

    def test_abstention_expectation_follows_answerability_only(self) -> None:
        for case in self.cases:
            self.assertEqual(
                case["abstention_expected"],
                case["answerability_status"] in {"insufficient_evidence", "out_of_scope"},
            )


if __name__ == "__main__":
    unittest.main()
