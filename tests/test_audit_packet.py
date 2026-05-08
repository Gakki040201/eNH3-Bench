from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.audit_packet import build_audit_packet, build_review_sheet_rows  # noqa: E402


class AuditPacketTests(unittest.TestCase):
    def test_audit_packet_includes_source_span_and_fields(self) -> None:
        spans = [
            {
                "span_id": "S001",
                "paper_id": "P001",
                "candidate_score": 6,
                "matched_keywords": ["NH3", "15N"],
                "text": "15N2 validation supports NH3 assignment.",
            }
        ]
        drafts = [
            {
                "span_id": "S001",
                "evidence_id": "E001",
                "paper_id": "P001",
                "source_span": "15N2 validation supports NH3 assignment.",
                "reaction_family": "eNRR",
                "nitrogen_source": "15N2",
                "isotope_validation": "yes",
                "reliability_label": "B",
                "evidence_type": "primary_claim",
                "draft_confidence": "medium",
            }
        ]
        packet = build_audit_packet(spans, drafts)
        self.assertIn("# eNH3-Bench Human Audit Packet", packet)
        self.assertIn("15N2 validation supports NH3 assignment.", packet)
        self.assertIn("`reaction_family`", packet)
        self.assertIn("candidate score", packet)

    def test_review_sheet_rows_have_expected_columns(self) -> None:
        rows = build_review_sheet_rows(
            [{"span_id": "S001", "candidate_score": 1}],
            [{"span_id": "S001", "evidence_id": "E001", "paper_id": "P001"}],
        )
        self.assertEqual(rows[0]["evidence_id"], "E001")
        self.assertIn("reliability_label", rows[0]["fields_to_check"])
        self.assertIn("include_in_gold", rows[0])


if __name__ == "__main__":
    unittest.main()
