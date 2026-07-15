from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import (
    _family_gate_coverage,
    build_context_packets,
    summarize_context_packets,
)
from enh3bench.evidence_linking import ORDERED_SOURCE_PROFILE
from enh3bench.source_ledger import build_ordered_source_ledger


class PacketLocalVsPaperGateCoverageTests(unittest.TestCase):
    def _packets(self, body: str, records: list[dict[str, object]]) -> list[dict[str, object]]:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text(body, encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            return build_context_packets(
                records, [], [], [], run_name="fixture",
                context_profile=ORDERED_SOURCE_PROFILE, source_ledger=ledger,
            )

    def test_performance_can_be_locally_sufficient_with_missing_paper_gates(self) -> None:
        body = "## Results\n\nThe ammonia Faradaic efficiency was 20%."
        target = _record("P1_S001", body, "The ammonia Faradaic efficiency was 20%.", "performance_claim")
        packet = self._packets(body, [target])[0]
        self.assertTrue(packet["packet_local_context_sufficient"])
        self.assertEqual(packet["claim_support_context_sufficient"], packet["packet_local_context_sufficient"])
        self.assertEqual(packet["packet_local_context_status"], "sufficient")
        self.assertEqual(packet["paper_gate_coverage_status"], "partial_observed")
        self.assertIn("ammonia_quantification", packet["paper_gate_coverage_missing"])
        self.assertNotIn("quantification_method", packet["packet_local_missing_types"])

    def test_family_gate_records_target_and_local_observations(self) -> None:
        body = (
            "## Results\n\nAmmonia was quantified by NMR.\n\n"
            "The ammonia Faradaic efficiency was 20% with 15N2 isotope validation.\n\n"
            "An Ar blank control was performed."
        )
        target = _record(
            "P1_S001", body,
            "The ammonia Faradaic efficiency was 20% with 15N2 isotope validation.",
            "performance_claim",
        )
        blank = _record("P1_S002", body, "An Ar blank control was performed.", "validation_claim")
        quant = _record("P1_S003", body, "Ammonia was quantified by NMR.", "validation_claim")
        packet = next(item for item in self._packets(body, [target, blank, quant]) if item["target_span_id"] == "P1_S001")
        coverage = packet["family_gate_coverage"]
        self.assertEqual(coverage["isotope_15N"]["status"], "observed_in_target")
        self.assertEqual(coverage["blank_control"]["status"], "observed_in_local_context")
        self.assertEqual(coverage["ammonia_quantification"]["status"], "observed_in_local_context")

    def test_family_gate_records_linked_evidence_and_supporting_span(self) -> None:
        target = {
            "source_span_id": "P1_S001", "source_text": "Faradaic efficiency was 20%.",
            "reaction_family": "eNRR",
        }
        evidence = [{
            "span_id": "P1_S002", "text": "Ammonia was quantified by NMR.",
            "paragraph_uid": "PAR_LINKED",
        }]
        coverage, observed, missing, status = _family_gate_coverage(
            target, evidence, None, {"paragraph_uid": "PAR_TARGET", "text": target["source_text"]}, None,
            applicable=True,
        )
        quantification = coverage["ammonia_quantification"]
        self.assertEqual(quantification["status"], "observed_in_linked_evidence")
        self.assertEqual(quantification["supporting_span_ids"], ["P1_S002"])
        self.assertIn("ammonia_quantification", observed)
        self.assertNotIn("ammonia_quantification", missing)
        self.assertEqual(status, "partial_observed")

    def test_negative_validation_statement_is_not_positive_support(self) -> None:
        body = "## Results\n\nNo ammonia was detected in the blank."
        packet = self._packets(
            body, [_record("P1_S001", body, "No ammonia was detected in the blank.", "validation_claim")]
        )[0]
        self.assertFalse(packet["packet_local_context_sufficient"])
        self.assertIn("positive_validation_evidence", packet["packet_local_missing_types"])

    def test_low_trust_context_is_not_applicable(self) -> None:
        body = "## References\n\n1. A cited ammonia paper."
        record = _record("P1_S001", body, "1. A cited ammonia paper.", "performance_claim")
        record.update({"text_class": "reference_list", "provenance_type": "reference", "is_primary_admissible": False})
        packet = self._packets(body, [record])[0]
        self.assertEqual(packet["packet_local_context_status"], "not_applicable")
        self.assertEqual(packet["paper_gate_coverage_status"], "not_evaluated")
        self.assertTrue(all(value["status"] == "not_applicable" for value in packet["family_gate_coverage"].values()))

    def test_reactor_claim_needs_a_local_reactor_signal_not_all_fields(self) -> None:
        body = "## Results\n\nA flow cell was operated for the experiment."
        packet = self._packets(
            body, [_record("P1_S001", body, "A flow cell was operated for the experiment.", "reactor_claim")]
        )[0]
        self.assertTrue(packet["packet_local_context_sufficient"])

    def test_summary_separates_local_and_paper_statuses(self) -> None:
        body = "## Results\n\nThe ammonia Faradaic efficiency was 20%."
        packets = self._packets(body, [_record("P1_S001", body, "The ammonia Faradaic efficiency was 20%.", "performance_claim")])
        summary = summarize_context_packets(packets, "fixture")
        self.assertEqual(summary["packet_local_applicable_count"], 1)
        self.assertEqual(summary["packet_local_sufficient_count"], 1)
        self.assertEqual(summary["paper_gate_coverage_partial_count"], 1)

    def test_v013_input_without_new_fields_remains_processable(self) -> None:
        body = "## Results\n\nThe ammonia Faradaic efficiency was 20%."
        record = _record("P1_S001", body, "The ammonia Faradaic efficiency was 20%.", "performance_claim")
        record.pop("is_primary_admissible")
        record["schema_version"] = "0.13"
        packet = self._packets(body, [record])[0]
        self.assertTrue(packet["packet_local_context_sufficient"])
        self.assertEqual(packet["claim_support_context_sufficient"], True)


def _record(span_id: str, body: str, text: str, claim_type: str) -> dict[str, object]:
    start = body.index(text)
    text_class = "primary_performance_with_validation" if claim_type == "validation_claim" else "primary_performance"
    return {
        "paper_id": "P1", "document_id": "P1", "source_span_id": span_id,
        "source_text": text, "source_start_offset": start, "source_end_offset": start + len(text),
        "text_class": text_class, "provenance_type": "body", "reaction_family": "eNRR",
        "is_primary_admissible": True, "claim_type": claim_type,
    }


if __name__ == "__main__":
    unittest.main()
