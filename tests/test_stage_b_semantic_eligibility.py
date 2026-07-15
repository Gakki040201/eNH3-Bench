from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import build_context_packets
from enh3bench.evidence_linking import ORDERED_SOURCE_PROFILE
from enh3bench.source_ledger import build_ordered_source_ledger


class StageBSemanticEligibilityTests(unittest.TestCase):
    def _packets(self, body: str, records: list[dict[str, object]]) -> list[dict[str, object]]:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text(body, encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            return build_context_packets(
                records, [], [], [], run_name="fixture",
                context_profile=ORDERED_SOURCE_PROFILE, source_ledger=ledger,
            )

    def test_external_claim_scope_and_ownership_are_hard_gates(self) -> None:
        body = "## Introduction\n\nSmith et al. reported an ammonia Faradaic efficiency of 20%."
        text = "Smith et al. reported an ammonia Faradaic efficiency of 20%."
        packet = self._packets(body, [_record("P1_S001", body, text, "eNRR")])[0]
        self.assertEqual(packet["document_scope"], "external_or_cited_work")
        self.assertEqual(packet["claim_ownership"], "external_or_cited_authors")
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertEqual(packet["packet_local_context_status"], "not_applicable")
        self.assertCountEqual(
            packet["primary_applicability_hard_gate_failures"],
            ["document_scope_not_target_document", "claim_not_owned_by_target_authors"],
        )

    def test_any_source_and_primary_admissible_gate_coverage_are_separate(self) -> None:
        body = (
            "## Results\n\nIn this work, we report an ammonia Faradaic efficiency of 20%.\n\n"
            "Smith et al. reported that ammonia was quantified by NMR."
        )
        target_text = "In this work, we report an ammonia Faradaic efficiency of 20%."
        cited_text = "Smith et al. reported that ammonia was quantified by NMR."
        records = [
            _record("P1_S001", body, target_text, "eNRR"),
            _record("P1_S002", body, cited_text, "eNRR", claim_type="validation_claim"),
        ]
        packet = next(item for item in self._packets(body, records) if item["target_span_id"] == "P1_S001")
        any_gate = packet["family_gate_coverage_any_source"]["ammonia_quantification"]
        primary_gate = packet["family_gate_coverage_primary_admissible"]["ammonia_quantification"]
        self.assertNotEqual(any_gate["status"], "missing")
        self.assertEqual(primary_gate["status"], "missing")
        cited = next(item for item in packet["evidence_items"] if item["span_id"] == "P1_S002")
        self.assertFalse(cited["primary_admissible_gate_source"])
        self.assertFalse(cited["primary_support"])

    def test_reaction_family_conflict_is_local_and_blocks_sufficiency(self) -> None:
        body = "## Results\n\nIn this work, the nitrate reduction reaction (NO3RR) produced ammonia with a Faradaic efficiency of 20%."
        text = "In this work, the nitrate reduction reaction (NO3RR) produced ammonia with a Faradaic efficiency of 20%."
        packet = self._packets(body, [_record("P1_S001", body, text, "eNRR")])[0]
        self.assertTrue(packet["local_reaction_family_conflict_any_source"])
        self.assertTrue(packet["local_reaction_family_conflict_primary_admissible"])
        self.assertIn("reaction_family_conflict", packet["packet_local_missing_types"])

    def test_paper_consensus_mismatch_alone_is_not_a_local_conflict(self) -> None:
        body = "## Results\n\nIn this work, N2 was reduced to ammonia with a Faradaic efficiency of 20%."
        text = "In this work, N2 was reduced to ammonia with a Faradaic efficiency of 20%."
        record = _record("P1_S001", body, text, "eNRR")
        record["paper_level_reaction_family"] = "NO3RR"
        record["reaction_family_conflict"] = True
        record["reaction_family_scope"] = "paper_consensus"
        record["reaction_family_signals"] = []
        packet = self._packets(body, [record])[0]
        self.assertFalse(packet["local_reaction_family_conflict_primary_admissible"])
        self.assertNotIn("reaction_family_conflict", packet["packet_local_missing_types"])


def _record(
    span_id: str,
    body: str,
    text: str,
    family: str,
    *,
    claim_type: str = "performance_claim",
) -> dict[str, object]:
    start = body.index(text)
    return {
        "paper_id": "P1", "document_id": "P1", "source_span_id": span_id,
        "source_text": text, "source_start_offset": start, "source_end_offset": start + len(text),
        "text_class": "primary_performance_with_validation" if claim_type == "validation_claim" else "primary_performance",
        "provenance_type": "body", "reaction_family": family,
        "reaction_family_confidence": "high", "reaction_family_scope": "explicit_span",
        "is_primary_admissible": True, "claim_type": claim_type,
    }


if __name__ == "__main__":
    unittest.main()
