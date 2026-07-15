from __future__ import annotations

import unittest

from enh3bench.context_packet import build_context_packets
from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE


class ContextFamilySpecificSufficiencyTests(unittest.TestCase):
    def test_enrr_gates_are_precise(self) -> None:
        complete = self._packet("eNRR", "Faradaic efficiency 20%; 15N2 isotope validation; Ar blank; NOx screening; contamination control; ammonia quantification by ion chromatography.")
        self.assertTrue(complete["claim_support_context_sufficient"])
        nitrate_only = self._packet("eNRR", "Faradaic efficiency 20%; nitrate reactant; 15N2 isotope; Ar blank; contamination control; ammonia quantification by ion chromatography.")
        self.assertIn("NOx_control", nitrate_only["context_missing_types"])

    def test_nitrate_nitrite_and_no_profiles_do_not_require_15n2(self) -> None:
        cases = {
            "NO3RR": "Faradaic efficiency 20%; nitrate feed; nitrogen balance; ammonia quantification by ion chromatography; competing product tracking analysis.",
            "NO2RR": "Faradaic efficiency 20%; nitrite feed; nitrogen balance; ammonia quantification by ion chromatography; competing product tracking analysis.",
            "NORR": "Faradaic efficiency 20%; NO gas feed; NOx balance; ammonia quantification by ion chromatography; competing product tracking analysis.",
        }
        for family, text in cases.items():
            with self.subTest(family=family):
                packet = self._packet(family, text)
                self.assertNotIn("isotope_validation", packet["context_missing_types"])
                self.assertTrue(packet["claim_support_context_sufficient"])

    def test_lithium_profile_uses_profile_operating_gate(self) -> None:
        packet = self._packet("LiNRR", "Faradaic efficiency 20%; 15N2 isotope validation; Ar blank; NOx screening; contamination control; ammonia quantification by NMR; current density and runtime reported.")
        self.assertTrue(packet["claim_support_context_sufficient"])

    def _packet(self, family: str, text: str) -> dict[str, object]:
        evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": text, "text_class": "primary_performance", "provenance_type": "body", "reaction_family": family, "is_primary_admissible": True}]
        return build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=HIERARCHICAL_LINKING_PROFILE)[0]


if __name__ == "__main__":
    unittest.main()
