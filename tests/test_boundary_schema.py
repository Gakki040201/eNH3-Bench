from __future__ import annotations

import unittest

from enh3bench.boundary_schema import (
    BOUNDARY_FIELDS,
    CLAIM_TYPES,
    HIDDEN_TAX_TYPES,
    SUPPORTED_BOUNDARIES,
    TEXT_CLASSES,
    boundary_rank,
    coerce_float,
    has_any_value,
    has_explicit_yes,
    max_boundary,
    normalize_yes_no,
)


class BoundarySchemaTests(unittest.TestCase):
    def test_constants_include_boundaryledger_values(self) -> None:
        self.assertIn("primary_performance_with_validation", TEXT_CLASSES)
        self.assertIn("process_partial", SUPPORTED_BOUNDARIES)
        self.assertIn("negative_evidence_claim", CLAIM_TYPES)
        self.assertIn("cell_metric", BOUNDARY_FIELDS)
        self.assertIn("measurement_matrix_tax", HIDDEN_TAX_TYPES)

    def test_normalize_yes_no(self) -> None:
        self.assertEqual(normalize_yes_no("confirmed"), "yes")
        self.assertEqual(normalize_yes_no("not reported"), "no")
        self.assertEqual(normalize_yes_no(""), "missing")
        self.assertEqual(normalize_yes_no("not specified"), "unclear")

    def test_record_helpers(self) -> None:
        record = {"isotope_validation": "yes", "blank_control": "unclear", "value": "12.5%"}
        self.assertTrue(has_explicit_yes(record, "isotope_validation"))
        self.assertFalse(has_explicit_yes(record, "blank_control"))
        self.assertTrue(has_any_value(record, "value"))
        self.assertFalse(has_any_value(record, "blank_control"))
        self.assertEqual(coerce_float("12.5%"), 12.5)
        self.assertIsNone(coerce_float("not numeric"))

    def test_boundary_ordering(self) -> None:
        self.assertLess(boundary_rank("product_admissibility"), boundary_rank("reactor_legibility"))
        self.assertEqual(max_boundary(["cell_metric", "product_admissibility"]), "cell_metric")
        self.assertEqual(max_boundary([]), "unsupported_or_secondary")


if __name__ == "__main__":
    unittest.main()
