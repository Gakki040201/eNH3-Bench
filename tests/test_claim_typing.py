from __future__ import annotations

import unittest

from enh3bench.claim_typing import (
    classify_claim_type,
    has_ammonia_quantification_signal,
    has_gas_purification_trap_signal,
)
from enh3bench.evidence_linking import classify_link_type
from enh3bench.context_packet import _family_gate_satisfied


class ClaimTypingTests(unittest.TestCase):
    def test_chronoamperometry_control_corrects_legacy_process_label(self) -> None:
        result = classify_claim_type({
            "source_text": "Chronoamperometry with a control electrode confirmed the nitrogenase response.",
            "provenance_type": "results",
            "claim_type": "process_claim",
        })
        self.assertEqual(result["semantic_claim_type"], "validation_claim")
        self.assertEqual(result["legacy_claim_type"], "process_claim")
        self.assertTrue(result["semantic_claim_type_conflict"])
        self.assertEqual(result["semantic_claim_type_confidence"], "high")

    def test_fea_nitrate_transport_corrects_legacy_process_label(self) -> None:
        result = classify_claim_type({
            "source_text": "FEA resolved nitrate transport and the reaction pathway near the electrode.",
            "provenance_type": "results",
            "claim_type": "process_claim",
        })
        self.assertEqual(result["semantic_claim_type"], "mechanism_claim")
        self.assertTrue(result["semantic_claim_type_conflict"])

    def test_h_cell_setup_is_reactor_not_legacy_process(self) -> None:
        result = classify_claim_type({
            "source_text": "The H-cell setup used separated cathodic and anodic chambers.",
            "provenance_type": "methods",
            "claim_type": "process_claim",
        })
        self.assertEqual(result["semantic_claim_type"], "reactor_claim")

    def test_perspective_recommendation_is_secondary_not_performance(self) -> None:
        result = classify_claim_type({
            "source_text": "We recommend a common reporting framework for future directions.",
            "document_genre": "perspective",
            "span_claim_scope": "target_document",
            "claim_type": "performance_claim",
            "provenance_type": "body",
        })
        self.assertEqual(result["semantic_claim_type"], "secondary_context_claim")
        self.assertTrue(result["semantic_claim_type_conflict"])

    def test_fe_and_rate_assessment_without_a_result_is_performance_context(self) -> None:
        result = classify_claim_type({
            "source_text": "We systematically assessed FEs and the NH3 rate for each catalyst.",
            "provenance_type": "results",
        })
        self.assertEqual(result["semantic_claim_type"], "performance_context_claim")
        self.assertFalse(result["performance_result_evidence"])
        self.assertEqual(result["legacy_claim_type"], "")
        self.assertFalse(result["ammonia_quantification_signal"])

    def test_gas_purification_trap_is_not_ammonia_quantification(self) -> None:
        text = "The N2 feed was passed through an acid trap to remove adventitious NH3 and NOx."
        self.assertTrue(has_gas_purification_trap_signal(text))
        self.assertFalse(has_ammonia_quantification_signal(text))
        result = classify_claim_type({"source_text": text, "provenance_type": "methods"})
        self.assertEqual(result["semantic_claim_type"], "gas_purification_or_capture_claim")
        self.assertEqual(classify_link_type({"source_text": text, "provenance_type": "methods"}), "context_hint")
        self.assertFalse(_family_gate_satisfied("ammonia_quantification", text.casefold(), {}))

    def test_nmr_measurement_is_ammonia_quantification(self) -> None:
        text = "Ammonia was quantified by 1H NMR using a calibration curve."
        self.assertTrue(has_ammonia_quantification_signal(text))
        self.assertEqual(
            classify_claim_type({"source_text": text, "provenance_type": "methods"})["semantic_claim_type"],
            "ammonia_quantification_claim",
        )
        self.assertEqual(classify_link_type({"source_text": text, "provenance_type": "methods"}), "quantification")

    def test_trapped_ammonia_can_be_quantified_when_analytical_method_is_explicit(self) -> None:
        text = "NH3 collected in the acid trap was quantified by ion chromatography."
        self.assertTrue(has_gas_purification_trap_signal(text))
        self.assertTrue(has_ammonia_quantification_signal(text))
        result = classify_claim_type({"source_text": text, "provenance_type": "methods"})
        self.assertEqual(result["semantic_claim_type"], "ammonia_quantification_claim")

    def test_structured_explicit_quantification_gate_remains_supported(self) -> None:
        record = {
            "source_text": "Analytical details are reported below.",
            "validation_gates": {"quantification_method": "explicit"},
        }
        self.assertTrue(has_ammonia_quantification_signal(record))

    def test_structured_quantification_cannot_override_explicit_text_negation(self) -> None:
        for text in (
            "No ammonia quantification was performed.",
            "NH3 was not measured.",
        ):
            with self.subTest(text=text):
                record = {
                    "source_text": text,
                    "validation_gates": {"ammonia_quantification": "explicit"},
                    "claim_type": "ammonia_quantification_claim",
                }
                result = classify_claim_type(record)
                self.assertTrue(result["structured_quantification_present"])
                self.assertTrue(result["structured_gate_text_conflict"])
                self.assertFalse(result["ammonia_quantification_signal"])
                self.assertNotEqual(result["semantic_claim_type"], "ammonia_quantification_claim")

        positive = classify_claim_type({
            "source_text": "Ammonia was quantified by ion chromatography.",
            "validation_gates": {"ammonia_quantification": "explicit"},
        })
        self.assertFalse(positive["structured_gate_text_conflict"])
        self.assertTrue(positive["ammonia_quantification_signal"])

    def test_nadh_ammonium_calibration_is_quantification(self) -> None:
        text = "NADH consumption was calibrated against NH4+ standards in the enzymatic ammonium assay."
        result = classify_claim_type({"source_text": text, "provenance_type": "methods"})
        self.assertTrue(result["ammonia_quantification_signal"])
        self.assertTrue(result["enzymatic_quantification_signal"])
        self.assertEqual(result["semantic_claim_type"], "ammonia_quantification_claim")

    def test_online_mass_spectrometry_ammonia_calibration_is_quantification(self) -> None:
        text = "Online mass spectrometry used an ammonia calibration curve for quantitative measurement."
        result = classify_claim_type({"source_text": text, "provenance_type": "methods"})
        self.assertTrue(result["ammonia_quantification_signal"])
        self.assertTrue(result["mass_spectrometry_quantification_signal"])

    def test_all_extended_methods_require_and_accept_ammonia_association(self) -> None:
        methods = (
            "GC-MS", "gas chromatography-mass spectrometry", "ammonia-selective electrode",
            "ammonium-selective electrode", "titration", "conductivity assay",
        )
        for method in methods:
            with self.subTest(method=method):
                text = f"Ammonia concentration was measured by {method} using calibration standards."
                self.assertTrue(has_ammonia_quantification_signal(text))
                self.assertEqual(
                    classify_claim_type({"source_text": text})["semantic_claim_type"],
                    "ammonia_quantification_claim",
                )
                self.assertFalse(has_ammonia_quantification_signal(
                    f"The {method} instrument was available for unrelated gas analysis."
                ))

    def test_generic_mass_spectrometry_or_calibration_without_ammonia_is_not_quantification(self) -> None:
        self.assertFalse(has_ammonia_quantification_signal(
            "Online mass spectrometry measured hydrogen and oxygen evolution products."
        ))
        self.assertFalse(has_ammonia_quantification_signal(
            "A generic calibration curve was prepared for the detector response."
        ))

    def test_purification_trap_terms_alone_remain_non_quantitative(self) -> None:
        for text in (
            "The gas purification train used an acid trap for ammonia.",
            "A base trap and capture vessel removed NH3 from the outlet.",
            "The scrubber removed ammonia before the reactor.",
        ):
            with self.subTest(text=text):
                self.assertTrue(has_gas_purification_trap_signal(text))
                self.assertFalse(has_ammonia_quantification_signal(text))


if __name__ == "__main__":
    unittest.main()
