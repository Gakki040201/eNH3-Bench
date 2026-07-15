from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import build_context_packets
from enh3bench.evidence_linking import ORDERED_SOURCE_PROFILE
from enh3bench.source_ledger import build_ordered_source_ledger


class SourceLedgerReferencePreservationTests(unittest.TestCase):
    def test_reference_paragraph_remains_ordered_and_never_primary_support(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = "# Paper\n\n## Results\n\nFaradaic efficiency 20%.\n\n## References\n\n1. Reference with 15N."
            root.joinpath("P1.md").write_text(body, encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            self.assertTrue(any(p["document_region"] == "references" for p in ledger.paragraphs_by_document["P1"]))
            evidence = [_record("S1", body, "Faradaic efficiency 20%.", "primary_performance", "body"), _record("S2", body, "1. Reference with 15N.", "reference_list", "reference")]
            packets = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=ORDERED_SOURCE_PROFILE, source_ledger=ledger)
            for packet in packets:
                for item in packet["evidence_items"]:
                    if item["provenance_type"] == "reference":
                        self.assertFalse(item["primary_support"])


def _record(span_id: str, body: str, text: str, text_class: str, provenance: str) -> dict[str, object]:
    start = body.index(text)
    return {"paper_id": "P1", "document_id": "P1", "source_span_id": span_id, "source_text": text, "source_start_offset": start, "source_end_offset": start + len(text), "text_class": text_class, "provenance_type": provenance, "reaction_family": "eNRR", "is_primary_admissible": provenance == "body"}


if __name__ == "__main__":
    unittest.main()
