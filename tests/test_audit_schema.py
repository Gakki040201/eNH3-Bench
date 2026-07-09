from __future__ import annotations

import unittest

from enh3bench.audit_schema import empty_human_fields_template, is_reviewed_record, validate_human_label_record


class AuditSchemaTests(unittest.TestCase):
    def test_empty_human_fields_are_not_reviewed(self) -> None:
        record = empty_human_fields_template()
        self.assertFalse(is_reviewed_record(record))
        valid, errors = validate_human_label_record(record)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_reviewed_status_missing_core_labels_is_invalid(self) -> None:
        record = empty_human_fields_template()
        record["human_review_status"] = "reviewed"
        valid, errors = validate_human_label_record(record)
        self.assertFalse(valid)
        self.assertTrue(any("human_text_class" in error for error in errors))
        self.assertFalse(is_reviewed_record(record))

    def test_invalid_human_boundary_label_is_rejected(self) -> None:
        record = empty_human_fields_template()
        record.update(
            {
                "human_review_status": "reviewed",
                "human_text_class": "primary_performance",
                "human_maximum_supported_boundary": "full_plant_claim",
                "human_admissibility_status": "accept",
                "human_experiment_decision": "priority_experiment",
            }
        )
        valid, errors = validate_human_label_record(record)
        self.assertFalse(valid)
        self.assertIn("invalid human_maximum_supported_boundary", "; ".join(errors))


if __name__ == "__main__":
    unittest.main()
