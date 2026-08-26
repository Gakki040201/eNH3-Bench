import math
import unittest

from enh3bench.linrr_predictor import assert_no_group_leakage, grouped_fold_indices
from enh3bench.linrr_predictor_v02 import FEATURE_SCHEMA, pipeline
from enh3bench.linrr_v02 import (
    apply_unit_safe_fields, assert_unit_safe_feature_schema, classify_context_role,
    context_can_supply_training, deterministic_hash, no_cross_paper_binding,
    normalize_concentration, parse_charge_temperature, rebuild_record,
)


class ChargeTemperatureTests(unittest.TestCase):
    def test_bare_c_is_not_temperature_or_uncontextual_charge(self):
        parsed = parse_charge_temperature("700 C")
        self.assertIsNone(parsed["temperature_C"])
        self.assertIsNone(parsed["total_charge_C"])

    def test_explicit_temperature(self):
        self.assertEqual(parse_charge_temperature("heated to 700 °C")["temperature_C"], 700.0)

    def test_common_charge_values(self):
        for value in (99, 198, 297, 700):
            parsed = parse_charge_temperature(f"after passing a charge of {value} C")
            self.assertEqual(parsed["total_charge_C"], float(value))
            self.assertIsNone(parsed["temperature_C"])


class UnitFamilyTests(unittest.TestCase):
    def test_mm_to_mol_l(self):
        value = normalize_concentration(125, "mM")
        self.assertEqual(value["mM"], 125)
        self.assertAlmostEqual(value["mol_L"], 0.125)

    def test_incompatible_units_not_molarized(self):
        for unit, family in (("vol%", "vol_percent"), ("wt%", "wt_percent"), ("ppm", "ppm")):
            value = normalize_concentration(2, unit)
            self.assertIsNone(value["mol_L"])
            self.assertEqual(value[family], 2)

    def test_legacy_universal_feature_removed(self):
        row = apply_unit_safe_fields({"proton_donor_concentration_raw_value": 1, "proton_donor_concentration_raw_unit": "vol%", "proton_donor_concentration_value": 1})
        self.assertIsNone(row["proton_donor_concentration_value"])
        self.assertIsNone(row["proton_donor_concentration_mol_L"])
        self.assertEqual(row["proton_donor_concentration_vol_percent"], 1)
        assert_unit_safe_feature_schema(FEATURE_SCHEMA)


class OwnershipBindingTests(unittest.TestCase):
    def test_cited_prior_study_cannot_supply_training(self):
        role = classify_context_role("A previous study reported 64% FE after 300 h.")
        self.assertEqual(role, "CITED_PRIOR_STUDY")
        self.assertFalse(context_can_supply_training(role))

    def test_review_background_cannot_create_target(self):
        role = classify_context_role("This review summarizes lithium-mediated nitrogen reduction.")
        self.assertEqual(role, "REVIEW_OR_BACKGROUND")
        self.assertFalse(context_can_supply_training(role))

    def test_same_experiment_and_same_paper_binding(self):
        rows = [{"record_id": "r", "paper_id": "P1", "experiment_binding_id": "P1::a::Table S1:row:2"}]
        no_cross_paper_binding(rows)
        with self.assertRaises(AssertionError):
            no_cross_paper_binding([{**rows[0], "experiment_binding_id": "P2::a::row"}])


class GroupedPreprocessingTests(unittest.TestCase):
    def test_group_kfold_no_paper_leakage(self):
        groups = ["P1", "P1", "P2", "P2", "P3", "P3", "P4", "P4", "P5", "P5"]
        folds = grouped_fold_indices(groups)
        assert_no_group_leakage(groups, folds)

    def test_processed_matrix_finite(self):
        import numpy as np
        categorical = list(FEATURE_SCHEMA["MODEL_R0"]["categorical"])
        numeric = list(FEATURE_SCHEMA["MODEL_R0"]["numeric"])
        X = [[None] * len(numeric) + ["__MISSING__"] * len(categorical), [1.0] * len(numeric) + ["x"] * len(categorical)]
        model = pipeline("Ridge", categorical, numeric)
        model.fit(X, [1.0, 2.0])
        matrix = model.named_steps["preprocess"].transform(X)
        if hasattr(matrix, "toarray"):
            matrix = matrix.toarray()
        self.assertTrue(np.isfinite(matrix).all())

    def test_deterministic_rebuild(self):
        source = {"record_id": "R", "paper_id": "P", "source_asset_id": "A", "source_locator": "page:1", "source_text_excerpt": "In this work we achieved 20% FE.", "model_eligible_fe": True, "fe_nh3_percent": 20.0}
        first, _ = rebuild_record(source)
        second, _ = rebuild_record(source)
        self.assertEqual(first, second)
        self.assertEqual(deterministic_hash([first]), deterministic_hash([second]))


if __name__ == "__main__":
    unittest.main()

