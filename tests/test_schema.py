from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.schema import (  # noqa: E402
    EvidenceRecord,
    PaperRecord,
    evidence_from_dict,
    evidence_to_dict,
    paper_from_dict,
    paper_to_dict,
    validate_evidence_record,
    validate_paper_record,
)


def make_valid_paper() -> PaperRecord:
    return PaperRecord(
        paper_id="P001",
        title="Validation protocol for electrochemical ammonia synthesis",
        doi="10.0000/example1",
        year=2026,
        journal="Example Protocols",
        article_type="protocol",
        open_access=True,
        source_file=None,
        notes="Example paper metadata.",
    )


def make_valid_evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="E001",
        paper_id="P001",
        source_span="The protocol requires 15N2 validation, blank controls, and NOx screening.",
        source_section="methods",
        reaction_family="eNRR",
        nitrogen_source="15N2",
        catalyst=None,
        catalyst_class=None,
        electrolyte=None,
        reactor_type=None,
        membrane=None,
        potential_value=None,
        potential_unit=None,
        potential_reference=None,
        current_density_mA_cm2=None,
        faradaic_efficiency_percent=None,
        nh3_yield_value=None,
        nh3_yield_unit=None,
        nh3_yield_normalized_value=None,
        nh3_yield_normalized_unit=None,
        energy_efficiency_percent=None,
        stability_hours=None,
        detection_method="indophenol blue and isotope NMR",
        isotope_validation="yes",
        blank_control="yes",
        contamination_control="yes",
        nox_screening="yes",
        reliability_label="A",
        evidence_type="control_experiment",
        gold_notes="Example validation evidence.",
    )


class SchemaTests(unittest.TestCase):
    def test_valid_paper_record(self) -> None:
        self.assertEqual(validate_paper_record(make_valid_paper()), [])

    def test_invalid_paper_article_type(self) -> None:
        paper = make_valid_paper()
        paper.article_type = "news"
        messages = validate_paper_record(paper)
        self.assertTrue(any("article_type" in message for message in messages))

    def test_valid_evidence_record(self) -> None:
        self.assertEqual(validate_evidence_record(make_valid_evidence()), [])

    def test_invalid_evidence_record_allowed_values(self) -> None:
        evidence = make_valid_evidence()
        evidence.reaction_family = "HER"
        evidence.reliability_label = "excellent"
        messages = validate_evidence_record(evidence)
        self.assertTrue(any("reaction_family" in message for message in messages))
        self.assertTrue(any("reliability_label" in message for message in messages))

    def test_empty_source_span_is_invalid(self) -> None:
        evidence = make_valid_evidence()
        evidence.source_span = " "
        messages = validate_evidence_record(evidence)
        self.assertTrue(any("source_span is required" in message for message in messages))

    def test_a_label_without_isotope_validation_warns(self) -> None:
        evidence = make_valid_evidence()
        evidence.isotope_validation = "unclear"
        messages = validate_evidence_record(evidence)
        self.assertTrue(any(message.startswith("warning:") for message in messages))

    def test_review_summary_a_label_warns(self) -> None:
        evidence = make_valid_evidence()
        evidence.evidence_type = "review_summary"
        messages = validate_evidence_record(evidence)
        self.assertTrue(any("review_summary" in message for message in messages))

    def test_paper_round_trip(self) -> None:
        paper = make_valid_paper()
        self.assertEqual(paper_from_dict(paper_to_dict(paper)), paper)

    def test_evidence_round_trip(self) -> None:
        evidence = make_valid_evidence()
        self.assertEqual(evidence_from_dict(evidence_to_dict(evidence)), evidence)


if __name__ == "__main__":
    unittest.main()
