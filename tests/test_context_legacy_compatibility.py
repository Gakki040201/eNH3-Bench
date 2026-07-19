from __future__ import annotations

import copy
import unittest

from enh3bench.context_packet import build_context_packets
from enh3bench.human_audit import AUDIT_FIELD_ORDER


class ContextLegacyCompatibilityTests(unittest.TestCase):
    def test_context_fields_do_not_enter_legacy_audit_columns(self) -> None:
        forbidden = {"stable_span_uid", "context_packet_id", "target_span_id", "previous_spans", "linked_performance_spans"}
        self.assertFalse(forbidden & set(AUDIT_FIELD_ORDER))

    def test_context_build_preserves_legacy_source_ids_and_inputs(self) -> None:
        evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "FE 20%", "text_class": "primary_performance", "provenance_type": "body"}]
        before = copy.deepcopy(evidence)
        packets = build_context_packets(evidence, [], [], [], run_name="fixture")
        self.assertEqual(evidence, before)
        self.assertEqual([packet["target_span_id"] for packet in packets], ["P1_S001"])


if __name__ == "__main__":
    unittest.main()
