from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import build_context_packets, summarize_context_packets
from enh3bench.evidence_linking import ORDERED_SOURCE_PROFILE
from enh3bench.source_ledger import build_ordered_source_ledger


class OrderedContextPacketTests(unittest.TestCase):
    def test_packet_uses_paragraph_links_and_claim_applicability(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = "# Paper\n\nFaradaic efficiency 20%.\n\n15N isotope validation and Ar blank.\n\n1. Reference."
            root.joinpath("P1.md").write_text(body, encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            evidence = [
                _record("P1_S001", body, "Faradaic efficiency 20%.", "primary_performance", "body"),
                _record("P1_S002", body, "15N isotope validation and Ar blank.", "protocol_guideline", "methods"),
                _record("P1_S003", body, "1. Reference.", "primary_performance", "reference"),
            ]
            packets = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=ORDERED_SOURCE_PROFILE, source_ledger=ledger)
            target = next(packet for packet in packets if packet["target_span_id"] == "P1_S001")
            reference = next(packet for packet in packets if packet["target_span_id"] == "P1_S003")
            self.assertEqual(target["context_packet_schema_version"], "1.3")
            self.assertEqual(target["next_paragraph"]["text"], "15N isotope validation and Ar blank.")
            self.assertTrue(target["claim_support_applicable"])
            self.assertFalse(reference["claim_support_applicable"])
            self.assertNotIn("full_body_text", target)
            self.assertEqual(reference["claim_support_context_sufficient"], False)
            summary = summarize_context_packets(packets, "fixture")
            self.assertEqual(summary["claim_support_applicable_count"], 1)
            self.assertEqual(summary["claim_support_not_applicable_count"], 2)
            self.assertEqual(summary["claim_support_context_insufficient_count"], 0)
            self.assertEqual(summary["packet_local_sufficient_count"], 1)


def _record(span_id: str, body: str, text: str, text_class: str, provenance: str) -> dict[str, object]:
    start = body.index(text)
    return {"paper_id": "P1", "document_id": "P1", "source_span_id": span_id, "source_text": text, "source_start_offset": start, "source_end_offset": start + len(text), "text_class": text_class, "provenance_type": provenance, "reaction_family": "eNRR", "is_primary_admissible": provenance in {"body", "methods"}}


if __name__ == "__main__":
    unittest.main()
