from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from enh3bench.e2e_eval_schema import (
    SELECTIVE_EVAL_PROFILE,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    make_case_id,
    make_human_review_id,
    make_judgment_id,
    make_output_id,
    paper_split,
    resolve_run_target,
)


class E2EEvalSchemaV016Tests(unittest.TestCase):
    def test_versions(self) -> None:
        self.assertEqual(SELECTIVE_EVAL_SCHEMA_VERSION, "0.16-selective-eval.1")
        self.assertEqual(SELECTIVE_EVAL_PROFILE, "selective_human_anchor_and_e2e_api_v1")

    def test_stable_case_id_and_prefix(self) -> None:
        value = make_case_id("P1", "D1", "paper_scope_classification")
        self.assertEqual(value, make_case_id("P1", "D1", "paper_scope_classification"))
        self.assertTrue(value.startswith("EC16_"))

    def test_run_name_independence(self) -> None:
        first = make_case_id("P1", "D1", "reaction_family_identification")
        second = make_case_id("P1", "D1", "reaction_family_identification")
        self.assertEqual(first, second)

    def test_output_judgment_and_human_id_prefixes(self) -> None:
        case_id = make_case_id("P1", "D1", "paper_scope_classification")
        self.assertTrue(make_output_id(case_id).startswith("EO16_"))
        self.assertTrue(make_judgment_id(case_id, "judge_1").startswith("MJ16_"))
        self.assertTrue(make_human_review_id(case_id, "reviewer_1").startswith("HR16_"))

    def test_reviewer_identity_does_not_enter_human_review_id(self) -> None:
        case_id = make_case_id("P1", "D1", "paper_scope_classification")
        self.assertEqual(
            make_human_review_id(case_id, "reviewer_1"),
            make_human_review_id(case_id, "reviewer_1"),
        )

    def test_paper_split_is_deterministic(self) -> None:
        self.assertEqual(paper_split(16, "P1"), paper_split(16, "P1"))
        self.assertIn(paper_split(16, "P1")[0], {"development", "holdout"})

    def test_clean_target_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                resolve_run_target(Path(temp), "../escape")
            with self.assertRaises(ValueError):
                resolve_run_target(Path("."), "valid_run")


if __name__ == "__main__":
    unittest.main()
