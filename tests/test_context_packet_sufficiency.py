from __future__ import annotations

import unittest

from enh3bench.context_packet import build_context_packets


class ContextPacketSufficiencyTests(unittest.TestCase):
    def test_primary_performance_with_linked_validation_and_quantification_is_sufficient(self) -> None:
        evidence, claims, provenance = _records(include_support=True)
        packets = build_context_packets(evidence, claims, [], provenance, run_name="fixture")
        target = next(packet for packet in packets if packet["target_span_id"] == "P1_S001")
        self.assertTrue(target["context_sufficient"])
        self.assertEqual(target["context_missing_types"], [])

    def test_primary_performance_missing_support_is_explicitly_insufficient(self) -> None:
        evidence, claims, provenance = _records(include_support=False)
        target = build_context_packets(evidence, claims, [], provenance, run_name="fixture")[0]
        self.assertFalse(target["context_sufficient"])
        self.assertIn("isotope_validation", target["context_missing_types"])
        self.assertIn("quantification_method", target["context_missing_types"])

    def test_reference_can_have_sufficient_context_without_positive_support(self) -> None:
        evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "1. Citation.", "text_class": "reference_list", "provenance_type": "reference", "reaction_family": "unclear"}]
        packet = build_context_packets(evidence, [], [], [], run_name="fixture")[0]
        self.assertTrue(packet["context_sufficient"])
        self.assertEqual(packet["target_span_boundary"], "unsupported_or_secondary")


def _records(include_support: bool) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Primary Faradaic efficiency 20% and NH3 yield.", "text_class": "primary_performance", "provenance_type": "body", "reaction_family": "eNRR", "is_primary_admissible": True}]
    if include_support:
        evidence.extend([
            {"paper_id": "P1", "source_span_id": "P1_S002", "source_text": "15N isotope validation with Ar blank, NOx nitrate nitrite screening and contamination control.", "text_class": "protocol_guideline", "provenance_type": "methods", "reaction_family": "eNRR", "is_primary_admissible": True},
            {"paper_id": "P1", "source_span_id": "P1_S003", "source_text": "Ammonia quantification by ion chromatography calibration.", "text_class": "protocol_guideline", "provenance_type": "methods", "reaction_family": "eNRR", "is_primary_admissible": True},
        ])
    claims = [{"paper_id": "P1", "source_span_id": "P1_S001", "maximum_supported_boundary": "cell_metric", "claim_type": "performance_claim", "validation_gates": {}}]
    provenance = [{"paper_id": "P1", "source_span_id": record["source_span_id"], "section_path": ["Results"], "provenance_type": record["provenance_type"], "is_primary_admissible": True} for record in evidence]
    return evidence, claims, provenance


if __name__ == "__main__":
    unittest.main()
