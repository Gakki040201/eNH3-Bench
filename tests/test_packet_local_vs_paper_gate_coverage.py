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
        self.assertEqual(coverage["isotope_15N"]["gate_detection_source"], "target_text")
        self.assertEqual(coverage["blank_control"]["gate_detection_source"], "local_text")

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
        self.assertEqual(quantification["gate_detection_source"], "linked_primary_evidence")
        self.assertIn("ammonia_quantification", observed)
        self.assertNotIn("ammonia_quantification", missing)
        self.assertEqual(status, "partial_observed")

    def test_structured_gate_conflict_is_missing_and_not_complete(self) -> None:
        target = {
            "source_span_id": "P1_S001",
            "source_text": "No isotope experiment was performed.",
            "reaction_family": "eNRR",
            "validation_gates": {"isotope_15N": "explicit"},
        }
        coverage, observed, missing, status = _family_gate_coverage(
            target, [], None, {"paragraph_uid": "PAR1", "text": target["source_text"]}, None,
            applicable=True,
        )
        isotope = coverage["isotope_15N"]
        self.assertEqual(isotope["status"], "conflict_in_target")
        self.assertEqual(isotope["gate_detection_source"], "structured_explicit")
        self.assertTrue(isotope["gate_conflict"])
        self.assertNotIn("isotope_15N", observed)
        self.assertIn("isotope_15N", missing)
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
        self.assertTrue({
            "document_genre_distribution", "span_claim_scope_distribution",
            "claim_ownership_distribution", "semantic_claim_type_distribution",
            "semantic_claim_type_conflict_count", "primary_semantic_eligibility_count",
            "hard_gate_failure_distribution", "off_target_reaction_conflict_count",
            "review_removed_from_primary_count", "perspective_removed_from_primary_count",
            "external_attribution_removed_count", "target_primary_gate_complete_count",
            "any_source_gate_complete_count", "quantification_signal_count", "gas_trap_only_count",
            "mass_spec_quantification_count", "enzymatic_quantification_count",
            "document_genre_inconsistent_document_count", "semantic_claim_type_conflict_matrix",
            "semantic_claim_type_conflict_by_document_genre",
            "semantic_claim_type_conflict_by_reaction_family",
            "semantic_claim_type_conflict_primary_eligible_count",
            "semantic_claim_type_conflict_not_applicable_count",
            "primary_semantic_eligible_by_document_genre",
            "primary_semantic_eligible_by_semantic_claim_type",
            "primary_semantic_eligible_by_reaction_family",
            "primary_semantic_eligible_by_provenance_type",
            "primary_semantic_eligible_by_ownership_confidence",
            "primary_semantic_eligible_by_semantic_type_confidence",
            "target_primary_gate_supported_by_nonprimary_count",
            "document_reaction_family_distribution", "effective_reaction_family_distribution",
            "reaction_family_correction_count", "document_target_family_conflict_count",
            "primary_eligible_by_effective_family", "primary_eligible_unclear_family_count",
            "performance_result_claim_count", "performance_context_claim_count",
            "quantitative_performance_primary_count", "FeS_false_performance_count",
            "performance_context_quantitative_primary_count",
            "primary_performance_without_result_evidence_count",
            "generic_isotope_false_15N_count", "NO_negation_false_source_count",
            "NOx_balance_negation_false_positive_count", "conflicted_gate_counted_as_observed_count",
        }.issubset(summary))
        self.assertEqual(summary["document_genre_inconsistent_document_count"], 0)
        self.assertEqual(summary["target_primary_gate_supported_by_nonprimary_count"], 0)
        self.assertEqual(summary["primary_semantic_eligible_by_document_genre"], {"primary_research": 1})
        self.assertEqual(summary["primary_semantic_eligible_by_semantic_claim_type"]["mechanism_claim"], 0)
        self.assertEqual(summary["primary_eligible_by_effective_family"], {"eNRR": 1})
        self.assertEqual(summary["quantitative_performance_primary_count"], 1)
        self.assertEqual(summary["FeS_false_performance_count"], 0)
        self.assertEqual(summary["generic_isotope_false_15N_count"], 0)
        self.assertEqual(summary["NO_negation_false_source_count"], 0)
        self.assertEqual(summary["NOx_balance_negation_false_positive_count"], 0)
        self.assertEqual(summary["performance_context_quantitative_primary_count"], 0)
        self.assertEqual(summary["primary_performance_without_result_evidence_count"], 0)
        self.assertEqual(summary["conflicted_gate_counted_as_observed_count"], 0)

    def test_v013_input_without_new_fields_remains_processable(self) -> None:
        body = "## Results\n\nThe ammonia Faradaic efficiency was 20%."
        record = _record("P1_S001", body, "The ammonia Faradaic efficiency was 20%.", "performance_claim")
        record.pop("is_primary_admissible")
        record["schema_version"] = "0.13"
        packet = self._packets(body, [record])[0]
        self.assertTrue(packet["packet_local_context_sufficient"])
        self.assertEqual(packet["claim_support_context_sufficient"], True)

    def test_document_genre_distribution_counts_each_document_once(self) -> None:
        body = "## Results\n\nThe ammonia Faradaic efficiency was 20%."
        packet = self._packets(
            body, [_record("P1_S001", body, "The ammonia Faradaic efficiency was 20%.", "performance_claim")]
        )[0]
        duplicate_span = {**packet, "target_span_id": "P1_S999", "context_packet_id": "CP_DUPLICATE"}
        summary = summarize_context_packets([packet, duplicate_span], "fixture")
        self.assertEqual(sum(summary["document_genre_distribution"].values()), 1)
        self.assertEqual(sum(summary["document_genre_span_distribution"].values()), 2)
        self.assertEqual(summary["document_genre_inconsistent_document_count"], 0)

        inconsistent = {**duplicate_span, "document_genre": "review"}
        inconsistent_summary = summarize_context_packets([packet, inconsistent], "fixture")
        self.assertEqual(inconsistent_summary["document_genre_inconsistent_document_count"], 1)

    def test_conflict_matrix_and_primary_cross_tables_are_auditable(self) -> None:
        body = "## Results\n\nThe ammonia Faradaic efficiency was 20%."
        packet = self._packets(
            body, [_record("P1_S001", body, "The ammonia Faradaic efficiency was 20%.", "performance_claim")]
        )[0]
        conflict = {
            **packet,
            "legacy_claim_type": "process_claim",
            "semantic_claim_type": "performance_claim",
            "semantic_claim_type_conflict": True,
        }
        summary = summarize_context_packets([conflict], "fixture")
        self.assertEqual(summary["semantic_claim_type_conflict_matrix"], {
            "process_claim": {"performance_claim": 1}
        })
        self.assertEqual(summary["semantic_claim_type_conflict_primary_eligible_count"], 1)
        self.assertEqual(summary["semantic_claim_type_conflict_not_applicable_count"], 0)
        self.assertEqual(summary["primary_semantic_eligible_by_semantic_claim_type"]["performance_claim"], 1)
        self.assertEqual(summary["primary_semantic_eligible_by_provenance_type"], {"body": 1})

    def test_primary_gate_audit_detects_nonprimary_target_support(self) -> None:
        body = "## Results\n\nAmmonia was quantified by NMR using a calibration curve."
        packet = self._packets(
            body,
            [_record(
                "P1_S001", body, "Ammonia was quantified by NMR using a calibration curve.",
                "performance_claim",
            )],
        )[0]
        invalid = {
            **packet,
            "target_is_primary_admissible": False,
            "family_gate_coverage_primary_admissible": {
                "ammonia_quantification": {
                    "status": "observed_in_target",
                    "supporting_span_ids": [packet["target_span_id"]],
                }
            },
        }
        summary = summarize_context_packets([invalid], "fixture")
        self.assertEqual(summary["target_primary_gate_supported_by_nonprimary_count"], 1)
        self.assertEqual(summary["non_primary_provenance_primary_semantic_eligible_count"], 1)


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
