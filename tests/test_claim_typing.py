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


if __name__ == "__main__":
    unittest.main()
