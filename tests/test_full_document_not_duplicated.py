from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import build_context_packets
from enh3bench.document_context import build_document_context_index
from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE


class FullDocumentNotDuplicatedTests(unittest.TestCase):
    def test_packet_references_document_and_omits_full_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = "# Paper\n\n## Results\n\nFaradaic efficiency was 20%.\n\nThis tail makes the complete document distinct."
            root.joinpath("P1.md").write_text(body, encoding="utf-8")
            index = build_document_context_index(root)
            document_body = index.documents_by_id["P1"]["body_text"]
            start = document_body.index("Faradaic")
            evidence = [{"paper_id": "P1", "document_id": "P1", "source_span_id": "P1_S001", "source_text": "Faradaic efficiency was 20%.", "source_start_offset": start, "source_end_offset": start + 29, "text_class": "primary_performance", "provenance_type": "body", "reaction_family": "eNRR", "is_primary_admissible": True}]
            packet = build_context_packets(evidence, [], [], [], run_name="fixture", context_profile=HIERARCHICAL_LINKING_PROFILE, document_context_index=index)[0]
            self.assertTrue(packet["full_document_available"])
            self.assertTrue(packet["document_ref"].endswith("P1.md"))
            self.assertNotIn("body_text", packet)
            self.assertNotEqual(json.dumps(packet, sort_keys=True), document_body)
            self.assertEqual(packet["target_mapping"]["confidence"], "high")


if __name__ == "__main__":
    unittest.main()
