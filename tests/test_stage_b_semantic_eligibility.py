from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import (
    _local_reaction_family_assessment,
    _off_target_reaction_assessment,
    _packet_local_assessment,
    build_context_packets,
)
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
            ["span_claim_scope_not_target_document", "claim_not_owned_by_target_authors"],
        )

    def test_perspective_protocol_span_is_target_owned_but_not_primary(self) -> None:
        body = "## Conclusion\n\nIn this perspective, we recommend a common validation protocol."
        text = "In this perspective, we recommend a common validation protocol."
        packet = self._packets(body, [
            _record("P1_S001", body, text, "eNRR", document_genre="perspective")
        ])[0]
        self.assertEqual(packet["document_genre"], "perspective")
        self.assertEqual(packet["span_claim_scope"], "target_document")
        self.assertEqual(packet["claim_ownership"], "target_authors")
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertEqual(packet["packet_local_context_status"], "not_applicable")
        self.assertIn("document_genre_not_primary_research", packet["primary_applicability_hard_gate_failures"])

    def test_review_mechanism_span_remains_secondary_for_primary_eligibility(self) -> None:
        body = "## Mechanisms\n\nOxygen vacancies alter adsorption energy and the reaction pathway."
        text = "Oxygen vacancies alter adsorption energy and the reaction pathway."
        packet = self._packets(body, [
            _record(
                "P1_S001", body, text, "eNRR", claim_type="process_claim", document_genre="review"
            )
        ])[0]
        self.assertEqual(packet["document_genre"], "review")
        self.assertEqual(packet["semantic_claim_type"], "mechanism_claim")
        self.assertTrue(packet["semantic_claim_type_conflict"])
        self.assertFalse(packet["primary_semantic_eligibility"])

    def test_current_study_performance_is_primary_when_all_hard_gates_pass(self) -> None:
        body = "## Results\n\nIn this work, the NH3 Faradaic efficiency reached 20%."
        text = "In this work, the NH3 Faradaic efficiency reached 20%."
        packet = self._packets(body, [_record("P1_S001", body, text, "eNRR")])[0]
        self.assertEqual(packet["document_genre"], "primary_research")
        self.assertEqual(packet["span_claim_scope"], "target_document")
        self.assertEqual(packet["semantic_claim_type"], "performance_result_claim")
        self.assertTrue(packet["quantitative_performance_evidence"])
        self.assertTrue(packet["primary_semantic_eligibility"])

    def test_performance_context_is_not_primary_eligible(self) -> None:
        body = "## Results\n\nIn this work, the catalyst showed high ammonia yield."
        text = "In this work, the catalyst showed high ammonia yield."
        packet = self._packets(body, [_record("P1_S001", body, text, "eNRR")])[0]
        self.assertEqual(packet["semantic_claim_type"], "performance_context_claim")
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertIn(
            "semantic_claim_type_not_primary_eligible",
            packet["primary_applicability_hard_gate_failures"],
        )

    def test_high_confidence_document_family_conflict_is_a_hard_gate(self) -> None:
        body = "## Results\n\nIn this work, the catalyst reached a Faradaic efficiency of 20%."
        text = "In this work, the catalyst reached a Faradaic efficiency of 20%."
        record = _record("P1_S001", body, text, "eNRR")
        record["paper_title"] = "Electrochemical ammonia synthesis via nitrate reduction"
        packet = self._packets(body, [record])[0]
        self.assertEqual(packet["document_reaction_family"], "NO3RR")
        self.assertEqual(packet["effective_reaction_family"], "NO3RR")
        self.assertTrue(packet["document_target_reaction_family_conflict"])
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertIn(
            "document_target_reaction_family_conflict",
            packet["primary_applicability_hard_gate_failures"],
        )

    def test_secondary_provenance_flag_is_a_strict_primary_hard_gate(self) -> None:
        body = "## Results\n\nIn this work, we report an ammonia Faradaic efficiency of 20%."
        text = "In this work, we report an ammonia Faradaic efficiency of 20%."
        record = _record("P1_S001", body, text, "eNRR")
        record["is_secondary_or_context"] = True
        packet = self._packets(body, [record])[0]
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertIn("target_is_secondary_or_context", packet["primary_applicability_hard_gate_failures"])
        self.assertEqual(packet["paper_gate_coverage_primary_admissible_status"], "not_evaluated")

    def test_co2rr_and_zn_air_table_is_off_target_for_ammonia_family(self) -> None:
        body = "## Results\n\nIn this work, the CO2RR Faradaic efficiency and Zn-air battery performance were compared."
        text = "In this work, the CO2RR Faradaic efficiency and Zn-air battery performance were compared."
        packet = self._packets(body, [_record("P1_S001", body, text, "eNRR")])[0]
        self.assertTrue(packet["local_off_target_reaction_conflict"])
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertIn("local_off_target_reaction_conflict", packet["primary_applicability_hard_gate_failures"])

    def test_co2rr_introduction_in_norr_corpus_is_off_target(self) -> None:
        body = "## Introduction\n\nIn this work, CO2RR achieved a Faradaic efficiency of 45%."
        text = "In this work, CO2RR achieved a Faradaic efficiency of 45%."
        packet = self._packets(body, [_record("P1_S001", body, text, "NORR")])[0]
        self.assertTrue(packet["local_off_target_reaction_conflict"])
        self.assertFalse(packet["primary_semantic_eligibility"])

    def test_all_named_off_target_systems_are_guarded(self) -> None:
        systems = (
            "CO2RR", "carbon dioxide reduction", "ORR", "oxygen reduction", "OER",
            "oxygen evolution", "HER", "hydrogen evolution", "water splitting",
            "Zn-air battery", "fuel cell", "PEMFC", "lithium-sulfur battery",
            "methanol oxidation", "formic acid oxidation",
        )
        for system in systems:
            with self.subTest(system=system):
                result = _off_target_reaction_assessment({
                    "source_text": f"The paragraph discusses {system} performance only.",
                    "reaction_family": "eNRR",
                })
                self.assertTrue(result["local_off_target_reaction_conflict"])

    def test_explicit_ammonia_reaction_subject_prevents_off_target_false_positive(self) -> None:
        result = _off_target_reaction_assessment({
            "source_text": "The nitrogen reduction reaction was compared with CO2RR performance.",
            "reaction_family": "eNRR",
        })
        self.assertFalse(result["local_off_target_reaction_conflict"])

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

    def test_explicit_target_family_corrects_legacy_without_a_local_conflict(self) -> None:
        body = "## Results\n\nIn this work, the nitrate reduction reaction (NO3RR) produced ammonia with a Faradaic efficiency of 20%."
        text = "In this work, the nitrate reduction reaction (NO3RR) produced ammonia with a Faradaic efficiency of 20%."
        packet = self._packets(body, [_record("P1_S001", body, text, "eNRR")])[0]
        self.assertEqual(packet["legacy_reaction_family"], "eNRR")
        self.assertEqual(packet["effective_reaction_family"], "NO3RR")
        self.assertTrue(packet["reaction_family_correction"])
        self.assertFalse(packet["local_reaction_family_conflict_primary_admissible"])

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

    def test_explicit_local_primary_evidence_family_mismatch_is_a_conflict(self) -> None:
        result = _local_reaction_family_assessment(
            {"source_span_id": "S1", "reaction_family": "eNRR", "source_text": "N2 reduction."},
            [{
                "span_id": "S2", "reaction_family": "NO3RR",
                "reaction_family_scope": "explicit_span", "reaction_family_confidence": "high",
                "paragraph_uid": "PAR1", "text": "Nitrate reduction to ammonia.",
                "primary_admissible_gate_source": True,
            }],
            [{"paragraph_uid": "PAR1", "text": "N2 reduction evidence."}],
            target_primary_admissible=True,
        )
        self.assertTrue(result["local_reaction_family_conflict_any_source"])
        self.assertTrue(result["local_reaction_family_conflict_primary_admissible"])
        self.assertEqual(result["local_reaction_family_conflict_span_ids"], ["S2"])

    def test_local_primary_family_conflict_blocks_primary(self) -> None:
        text = "The NH3 Faradaic efficiency reached 20%."
        target = {
            "source_span_id": "S1", "source_text": text,
            "provenance_type": "body", "text_class": "primary_performance",
            "reaction_family": "eNRR", "reaction_family_confidence": "high",
            "reaction_family_scope": "explicit_span", "claim_type": "performance_claim",
            "document_genre": "primary_research", "span_claim_scope": "target_document",
            "claim_ownership": "target_authors", "is_primary_admissible": True,
            "is_secondary_or_context": False, "is_reject_or_low_trust": False,
            "source_mapping_method": "explicit_verified", "source_mapping_confidence": "high",
            "offset_text_match": True,
        }
        assessment = _packet_local_assessment(
            target,
            {"paragraph_uid": "PAR_TARGET", "text": text},
            None,
            {"paragraph_uid": "PAR_LINK", "text": "Li-mediated N2 reduction evidence."},
            {"section_uid": "SEC1", "section_type": "results"},
            [{
                "span_id": "S2", "paragraph_uid": "PAR_LINK",
                "text": "Li-mediated N2 reduction evidence.",
                "reaction_family": "LiNRR", "effective_reaction_family": "LiNRR",
                "reaction_family_scope": "explicit_span", "reaction_family_confidence": "high",
                "primary_admissible_gate_source": True,
            }],
        )
        self.assertTrue(assessment["local_reaction_family_conflict_primary_admissible"])
        self.assertFalse(assessment["applicable"])
        self.assertIn("local_primary_reaction_family_conflict", assessment["hard_gate_failures"])

    def test_structured_quantification_text_conflict_is_a_hard_gate(self) -> None:
        body = "## Results\n\nNo ammonia quantification was performed."
        text = "No ammonia quantification was performed."
        record = _record(
            "P1_S001", body, text, "eNRR", claim_type="ammonia_quantification_claim"
        )
        record["validation_gates"] = {"ammonia_quantification": "explicit"}
        packet = self._packets(body, [record])[0]
        self.assertTrue(packet["structured_gate_text_conflict"])
        self.assertFalse(packet["ammonia_quantification_signal"])
        self.assertFalse(packet["primary_semantic_eligibility"])
        self.assertIn("structured_gate_text_conflict", packet["primary_applicability_hard_gate_failures"])


def _record(
    span_id: str,
    body: str,
    text: str,
    family: str,
    *,
    claim_type: str = "performance_claim",
    document_genre: str = "primary_research",
) -> dict[str, object]:
    start = body.index(text)
    return {
        "paper_id": "P1", "document_id": "P1", "source_span_id": span_id,
        "source_text": text, "source_start_offset": start, "source_end_offset": start + len(text),
        "text_class": "primary_performance_with_validation" if claim_type == "validation_claim" else "primary_performance",
        "provenance_type": "body", "reaction_family": family,
        "reaction_family_confidence": "high", "reaction_family_scope": "explicit_span",
        "is_primary_admissible": True, "is_secondary_or_context": False,
        "is_reject_or_low_trust": False, "claim_type": claim_type,
        "document_genre": document_genre,
    }


if __name__ == "__main__":
    unittest.main()
