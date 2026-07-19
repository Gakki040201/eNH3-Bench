from __future__ import annotations

import unittest

from enh3bench.audit_schema import AUDIT_SCHEMA_VERSION
from enh3bench.context_packet import build_context_packets
from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE, KEYWORD_LINKING_PROFILE
from enh3bench.human_audit import AUDIT_FIELD_ORDER


class HierarchicalContextLegacyCompatibilityTests(unittest.TestCase):
    def test_profiles_are_independent_and_legacy_audit_unchanged(self) -> None:
        evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Faradaic efficiency 20%.", "text_class": "primary_performance", "provenance_type": "body", "reaction_family": "eNRR"}]
        legacy = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=KEYWORD_LINKING_PROFILE)[0]
        hierarchical = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=HIERARCHICAL_LINKING_PROFILE)[0]
        self.assertEqual(legacy["context_packet_schema_version"], "1.0")
        self.assertEqual(hierarchical["context_packet_schema_version"], "1.1")
        self.assertEqual(legacy["target_span_id"], hierarchical["target_span_id"])
        self.assertEqual(AUDIT_SCHEMA_VERSION, "0.13")
        self.assertNotIn("evidence_items", AUDIT_FIELD_ORDER)


if __name__ == "__main__":
    unittest.main()
