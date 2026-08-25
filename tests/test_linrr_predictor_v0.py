from __future__ import annotations

import unittest

from enh3bench.linrr_predictor import assert_no_group_leakage, grouped_fold_indices, modeling_gate, paper_group, train_grouped_models


def records(rows: int, groups: int):
    return [
        {"record_id": f"R{i}", "paper_id": f"P{i % groups:04d}", "provisional_bundle_id": None, "source_bundle_id": f"B{i % groups}", "fe_nh3_percent": float(i)}
        for i in range(rows)
    ]


class LiNRRPredictorV0Tests(unittest.TestCase):
    def test_group_kfold_has_no_paper_leakage(self):
        rows = records(30, 6)
        groups = [paper_group(row) for row in rows]
        folds = grouped_fold_indices(groups)
        assert_no_group_leakage(groups, folds)
        for train, test in folds:
            self.assertFalse({groups[i] for i in train} & {groups[i] for i in test})

    def test_same_paper_never_appears_in_train_and_test(self):
        groups = ["P1", "P1", "P2", "P2", "P3", "P3", "P4", "P4", "P5", "P5"]
        for train, test in grouped_fold_indices(groups):
            self.assertTrue(all(group not in {groups[i] for i in train} for group in {groups[i] for i in test}))

    def test_training_gate_refuses_under_25_rows(self):
        gate = modeling_gate(records(24, 6))
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["status"], "INSUFFICIENT_MODELING_DATA")

    def test_refusal_still_exports_declared_feature_schema(self):
        result = train_grouped_models(records(24, 6))
        self.assertFalse(result["gate"]["passed"])
        self.assertEqual(result["feature_schema"]["MODEL_R"]["categorical"][0], "lithium_salt")
        self.assertIn("paper_id", result["feature_schema"]["excluded_predictive_fields"])

    def test_training_gate_refuses_under_5_papers(self):
        gate = modeling_gate(records(30, 4))
        self.assertFalse(gate["passed"])
        self.assertIn("unique paper groups", gate["reasons"][0])

    def test_formal_training_uses_grouped_oof_predictions(self):
        rows = records(25, 5)
        for index, row in enumerate(rows):
            row.update({"eligibility_tier": "TIER_B", "lithium_salt": "LiBF4" if index % 2 else "LiClO4", "solvent": "THF", "current_density_mA_cm2": float(index + 1)})
        result = train_grouped_models(rows)
        self.assertTrue(result["gate"]["passed"])
        self.assertEqual({metric["model"] for metric in result["metrics"]}, {"DummyRegressor", "Ridge", "RandomForestRegressor"})
        self.assertEqual(len(result["predictions"]), 75)
        for prediction in result["predictions"]:
            self.assertEqual(prediction["paper_group"], rows[int(prediction["record_id"][1:])]["paper_id"])


if __name__ == "__main__":
    unittest.main()
