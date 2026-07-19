from __future__ import annotations

import json
import unittest

from enh3bench.context_packet import build_context_packets, summarize_context_packets
from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE


class ContextUniqueEvidenceSerializationTests(unittest.TestCase):
    def test_multi_role_text_is_serialized_once(self) -> None:
        evidence = [
            _record("P1_S001", "Faradaic efficiency 20%."),
            _record("P1_S002", "Unique support phrase: 15N isotope and ammonia quantification by ion chromatography."),
        ]
        packets = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=HIERARCHICAL_LINKING_PROFILE)
        packet = packets[0]
        self.assertEqual(len(packet["evidence_items"]), 1)
        self.assertEqual(set(packet["evidence_items"][0]["link_roles"]), {"validation", "quantification"})
        self.assertEqual(json.dumps(packet, sort_keys=True).count("Unique support phrase"), 1)
        summary = summarize_context_packets(packets, "fixture")
        self.assertEqual(summary["duplicate_serialized_span_count"], 0)
        self.assertEqual(summary["cross_paper_link_count"], 0)


def _record(span_id: str, text: str) -> dict[str, object]:
    return {"paper_id": "P1", "document_id": "P1", "source_span_id": span_id, "source_text": text, "section_path": ["Results"], "provenance_type": "body", "text_class": "primary_performance", "is_primary_admissible": True, "reaction_family": "eNRR"}


if __name__ == "__main__":
    unittest.main()
