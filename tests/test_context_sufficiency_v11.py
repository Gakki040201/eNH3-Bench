from __future__ import annotations

import unittest

from enh3bench.context_packet import build_context_packets
from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE


class ContextSufficiencyV11Tests(unittest.TestCase):
    def test_reference_is_classifiable_but_never_claim_support_sufficient(self) -> None:
        evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "1. Citation.", "text_class": "reference_list", "provenance_type": "reference", "reaction_family": "unclear"}]
        packet = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=HIERARCHICAL_LINKING_PROFILE)[0]
        self.assertTrue(packet["classification_context_sufficient"])
        self.assertFalse(packet["claim_support_context_sufficient"])
        self.assertFalse(packet["context_sufficient"])
        self.assertEqual(packet["context_purpose"], "classification")

    def test_context_hints_do_not_upgrade_primary_claim(self) -> None:
        evidence = [
            {"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Faradaic efficiency 20%.", "text_class": "primary_performance", "provenance_type": "body", "reaction_family": "eNRR", "is_primary_admissible": True},
            {"paper_id": "P1", "source_span_id": "P1_S002", "source_text": "15N isotope and controls in a citation.", "text_class": "reference_list", "provenance_type": "reference", "reaction_family": "eNRR"},
        ]
        packet = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=HIERARCHICAL_LINKING_PROFILE)[0]
        self.assertFalse(packet["claim_support_context_sufficient"])
        self.assertIn("isotope_validation", packet["context_missing_types"])


if __name__ == "__main__":
    unittest.main()
