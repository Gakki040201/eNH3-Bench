from __future__ import annotations

import unittest

from enh3bench.linrr_v01_audit import (
    build_tier_c_terminal_status,
    numeric_unit_audit,
    ridge_oof_diagnostics,
    validate_terminal_statuses,
)


def tier_c(record_id: str, flags=None):
    return {"record_id": record_id, "eligibility_tier": "TIER_C", "ambiguity_flags": flags or [], "missing_required_fields": ["electrolyte_defined"]}


def final(record_id: str, tier: str = "TIER_C", eligible: bool = False, conflict=None):
    return {"record_id": record_id, "eligibility_tier": tier, "model_eligible_fe": eligible, "source_conflict_classification": conflict, "missing_required_fields": ["electrolyte_defined"]}


def model_rows():
    rows = []
    for index in range(25):
        rows.append({
            "record_id": f"R{index:02d}", "paper_id": f"P{index % 5}", "fe_nh3_percent": float(10 + index),
            "lithium_salt": "LiBF4", "solvent": "THF", "proton_donor": "ethanol",
            "lithium_salt_concentration_mol_L": 1.0, "proton_donor_concentration_value": 0.1,
            "proton_donor_concentration_unit": "M", "current_density_mA_cm2": float(index + 1),
            "duration_h": 1.0, "model_eligible_fe": True, "eligibility_tier": "TIER_B",
        })
    return rows


class LiNRRV01AuditTests(unittest.TestCase):
    def test_terminal_statuses_are_mutually_exclusive_and_sum(self):
        original = [tier_c("AUTO"), tier_c("HUMAN", ["TARGET_OWNERSHIP_UNCLEAR"]), tier_c("MERGED"), tier_c("REJECT"), tier_c("REMAINS")]
        finals = {
            "AUTO": final("AUTO", "TIER_B", True),
            "HUMAN": final("HUMAN"),
            "MERGED": final("MERGED"),
            "REJECT": final("REJECT", "EXCLUDED"),
            "REMAINS": final("REMAINS"),
        }
        rows = build_tier_c_terminal_status(original, finals, {"MERGED": {"canonical_record_id": "CANON"}}, {"AUTO", "HUMAN", "MERGED", "REJECT", "REMAINS"})
        counts = validate_terminal_statuses(rows, 5)
        self.assertEqual(sum(counts.values()), 5)
        self.assertEqual(set(counts.values()), {1})
        self.assertEqual(len({row["record_id"] for row in rows}), 5)

    def test_auto_resolved_is_not_unresolved_human_review(self):
        rows = build_tier_c_terminal_status([tier_c("R")], {"R": final("R", "TIER_B", True)}, {}, {"R"})
        self.assertEqual(rows[0]["terminal_status"], "AUTO_RESOLVED")
        self.assertFalse(rows[0]["requires_human_review"])

    def test_review_packet_retention_does_not_imply_unresolved_review(self):
        rows = build_tier_c_terminal_status([tier_c("R")], {"R": final("R", "TIER_B", True)}, {}, {"R"})
        self.assertTrue(rows[0]["review_packet_retained"])
        self.assertFalse(rows[0]["requires_human_review"])

    def test_ridge_diagnostics_preserve_group_split_and_no_paper_leakage(self):
        _, folds, preprocessing = ridge_oof_diagnostics(model_rows())
        self.assertFalse(preprocessing["group_leakage"])
        for fold in folds:
            self.assertFalse(set(fold["train_groups"]) & set(fold["test_groups"]))

    def test_numeric_preprocessing_contains_no_nonfinite_values(self):
        oof, _, preprocessing = ridge_oof_diagnostics(model_rows())
        self.assertTrue(preprocessing["processed_numeric_and_full_matrix_all_finite"])
        self.assertTrue(all(row["predicted_fe"] == row["predicted_fe"] for row in oof))

    def test_unit_normalized_features_do_not_mix_incompatible_units(self):
        audit = numeric_unit_audit(model_rows())
        incompatible = [issue for issue in audit["issues"] if issue["type"] == "INCOMPATIBLE_UNIT_MIX"]
        self.assertEqual(incompatible, [])
        self.assertTrue(audit["only_canonical_numeric_features_enter_model"])

    def test_duplicate_terminal_record_id_is_rejected(self):
        with self.assertRaises(AssertionError):
            build_tier_c_terminal_status([tier_c("R"), tier_c("R")], {"R": final("R")}, {}, set())


if __name__ == "__main__":
    unittest.main()
