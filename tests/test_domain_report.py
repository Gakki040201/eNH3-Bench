from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.domain_report import high_risk_records, render_domain_report, summarize_domain_records  # noqa: E402


class DomainReportTests(unittest.TestCase):
    def test_counts_and_validation_coverage(self) -> None:
        summary = summarize_domain_records(_records())
        self.assertEqual(summary["evidence_records"], 2)
        self.assertEqual(summary["unique_papers"], 2)
        self.assertEqual(summary["reaction_family"]["LiNRR"], 1)
        self.assertEqual(summary["validation_controls"]["nox_screening"]["unclear"], 1)
        self.assertEqual(summary["metric_availability"]["FE present"], 2)

    def test_high_risk_records_are_listed(self) -> None:
        risks = high_risk_records(_records())
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]["evidence_id"], "E002")

    def test_markdown_contains_sections(self) -> None:
        report = render_domain_report(_records())
        self.assertIn("# eNH3-Bench Domain Report", report)
        self.assertIn("Validation Control Coverage", report)
        self.assertIn("High-Risk Evidence", report)


def _records() -> list[dict]:
    return [
        {
            "evidence_id": "E001",
            "paper_id": "P001",
            "reaction_family": "LiNRR",
            "evidence_type": "primary_claim",
            "reliability_label": "B",
            "isotope_validation": "yes",
            "blank_control": "yes",
            "contamination_control": "yes",
            "nox_screening": "yes",
            "faradaic_efficiency_percent": 62.0,
            "nh3_yield_value": 10.5,
            "stability_hours": None,
            "energy_efficiency_percent": None,
            "potential_value": None,
            "source_span": "Primary evidence.",
        },
        {
            "evidence_id": "E002",
            "paper_id": "P002",
            "reaction_family": "NO3RR",
            "evidence_type": "primary_claim",
            "reliability_label": "D",
            "isotope_validation": "not_applicable",
            "blank_control": "unclear",
            "contamination_control": "unclear",
            "nox_screening": "unclear",
            "faradaic_efficiency_percent": 80.0,
            "nh3_yield_value": None,
            "stability_hours": None,
            "energy_efficiency_percent": None,
            "potential_value": -0.3,
            "source_span": "Nitrate evidence.",
        },
    ]


if __name__ == "__main__":
    unittest.main()
