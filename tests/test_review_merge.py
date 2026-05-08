from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.review_merge import merge_reviewed_gold  # noqa: E402


def draft(evidence_id: str, label: str = "D") -> dict:
    return {
        "evidence_id": evidence_id,
        "paper_id": "P001",
        "source_span": "Supported source span.",
        "source_section": "results",
        "reaction_family": "eNRR",
        "nitrogen_source": "15N2",
        "catalyst": None,
        "catalyst_class": None,
        "electrolyte": None,
        "reactor_type": None,
        "membrane": None,
        "potential_value": None,
        "potential_unit": None,
        "potential_reference": None,
        "current_density_mA_cm2": None,
        "faradaic_efficiency_percent": None,
        "nh3_yield_value": None,
        "nh3_yield_unit": None,
        "nh3_yield_normalized_value": None,
        "nh3_yield_normalized_unit": None,
        "energy_efficiency_percent": None,
        "stability_hours": None,
        "detection_method": None,
        "isotope_validation": "yes",
        "blank_control": "yes",
        "contamination_control": "unclear",
        "nox_screening": "unclear",
        "reliability_label": label,
        "evidence_type": "primary_claim",
        "gold_notes": "Initial note.",
        "machine_notes": "Machine draft; requires human verification.",
    }


class ReviewMergeTests(unittest.TestCase):
    def test_merge_includes_accepted_and_excludes_rejected(self) -> None:
        drafts = [draft("E001"), draft("E002")]
        rows = [
            {
                "evidence_id": "E001",
                "human_decision": "accept",
                "include_in_gold": "",
                "reliability_override": "B",
                "correction_notes": "Verified against source.",
            },
            {
                "evidence_id": "E002",
                "human_decision": "reject",
                "include_in_gold": "true",
                "reliability_override": "",
                "correction_notes": "Unsupported.",
            },
        ]
        merged = merge_reviewed_gold(drafts, rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["evidence_id"], "E001")
        self.assertEqual(merged[0]["reliability_label"], "B")
        self.assertIn("Verified against source.", merged[0]["gold_notes"])
        self.assertNotIn("machine_notes", merged[0])

    def test_include_in_gold_true_includes_blank_decision(self) -> None:
        merged = merge_reviewed_gold(
            [draft("E003")],
            [
                {
                    "evidence_id": "E003",
                    "human_decision": "",
                    "include_in_gold": "yes",
                    "reliability_override": "",
                    "correction_notes": "",
                }
            ],
        )
        self.assertEqual(len(merged), 1)


if __name__ == "__main__":
    unittest.main()
