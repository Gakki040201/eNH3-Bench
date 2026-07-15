from __future__ import annotations

import copy
import unittest

from enh3bench.context_packet import build_context_packets, summarize_context_packets


class ContextPacketTests(unittest.TestCase):
    def test_one_packet_per_target_and_required_fields(self) -> None:
        evidence, claims, provenance = _fixture()
        before = copy.deepcopy(evidence)
        packets = build_context_packets(evidence, claims, [], provenance, run_name="fixture")
        self.assertEqual(len(packets), len(evidence))
        self.assertEqual(evidence, before)
        packet = packets[0]
        for field in ("context_packet_schema_version", "context_packet_id", "target_stable_span_uid", "previous_spans", "context_hint_spans", "warnings"):
            self.assertIn(field, packet)
        self.assertEqual(packet["context_packet_schema_version"], "1.0")

    def test_summary_has_zero_cross_paper_and_low_trust_primary_support(self) -> None:
        evidence, claims, provenance = _fixture()
        packets = build_context_packets(evidence, claims, [], provenance, run_name="fixture")
        summary = summarize_context_packets(packets, "fixture")
        self.assertEqual(summary["packet_count"], len(evidence))
        self.assertEqual(summary["paper_count"], 1)
        self.assertEqual(summary["cross_paper_link_count"], 0)
        self.assertEqual(summary["reference_primary_support_count"], 0)
        self.assertEqual(summary["caption_primary_support_count"], 0)
        self.assertEqual(summary["review_table_primary_support_count"], 0)


def _fixture() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    evidence = [
        _record("P1_S001", "Primary FE 20% and NH3 yield.", "primary_performance", "body"),
        _record("P1_S002", "15N isotope, Ar blank, NOx and contamination control.", "protocol_guideline", "methods"),
        _record("P1_S003", "Ion chromatography calibration for ammonia quantification.", "protocol_guideline", "methods"),
        _record("P1_S004", "1. Reference citation with FE 90%.", "reference_list", "reference"),
    ]
    claims = [{"paper_id": "P1", "source_span_id": "P1_S001", "maximum_supported_boundary": "cell_metric", "claim_type": "performance_claim", "validation_gates": {}}]
    provenance = [{"paper_id": record["paper_id"], "source_span_id": record["source_span_id"], "section_path": ["Results" if index == 0 else "Methods"], "section_heading": "Results" if index == 0 else "Methods", "provenance_type": record["provenance_type"], "is_primary_admissible": record["provenance_type"] in {"body", "methods"}} for index, record in enumerate(evidence)]
    return evidence, claims, provenance


def _record(span_id: str, text: str, text_class: str, provenance: str) -> dict[str, object]:
    return {"paper_id": "P1", "source_span_id": span_id, "source_text": text, "text_class": text_class, "provenance_type": provenance, "reaction_family": "eNRR", "paper_level_reaction_family": "eNRR", "is_primary_admissible": provenance in {"body", "methods"}}


if __name__ == "__main__":
    unittest.main()
