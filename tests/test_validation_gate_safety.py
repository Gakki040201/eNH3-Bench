from __future__ import annotations

import unittest

from enh3bench.validation_gates import detect_validation_gate


class ValidationGateSafetyTests(unittest.TestCase):
    def test_uppercase_no_feed_does_not_negate_ammonia_quantification(self) -> None:
        text = "NO gas feed; ammonia quantification by ion chromatography."
        result = detect_validation_gate("ammonia_quantification", text)
        self.assertTrue(result["satisfied"])
        self.assertFalse(result["gate_conflict"])

    def test_15n_requires_explicit_nitrogen_15(self) -> None:
        for text in ("15N2 validation", "15NH3 was detected", "nitrogen-15 labelled nitrogen"):
            with self.subTest(text=text):
                self.assertTrue(detect_validation_gate("isotope_15N", text)["satisfied"])
        for text in ("an isotope experiment", "isotope-labelled material", "carbon isotope", "deuterium isotope"):
            with self.subTest(text=text):
                self.assertFalse(detect_validation_gate("isotope_15N", text)["satisfied"])

    def test_structured_15n_cannot_mask_text_negation(self) -> None:
        result = detect_validation_gate(
            "isotope_15N",
            "No isotope experiment was performed.",
            {"validation_gates": {"isotope_15N": "explicit"}},
        )
        self.assertFalse(result["satisfied"])
        self.assertTrue(result["gate_conflict"])
        self.assertEqual(result["gate_detection_source"], "structured_explicit")
        self.assertIn("structured_explicit_15N", result["gate_detection_signals"])

    def test_no_source_preserves_case_and_negation(self) -> None:
        for text in ("NO", "nitric oxide", "10% NO in Ar", "NO feed", "nitric-oxide feed"):
            with self.subTest(text=text):
                self.assertTrue(detect_validation_gate("NO_source_defined", text)["satisfied"])
        for text in ("no gas was supplied", "no feed was used", "no source was identified", "no concentration was reported"):
            with self.subTest(text=text):
                self.assertFalse(detect_validation_gate("NO_source_defined", text)["satisfied"])

    def test_nox_balance_has_negation_guard(self) -> None:
        for text in ("NO mass balance", "nitric oxide mass balance", "NOx balance", "nitrogen-oxide material balance"):
            with self.subTest(text=text):
                self.assertTrue(detect_validation_gate("NOx_balance", text)["satisfied"])
        for text in (
            "no mass balance", "no mass balance was reported", "without a mass balance",
            "mass balance was not performed", "No NOx balance was reported",
            "NO mass balance was not performed",
        ):
            with self.subTest(text=text):
                self.assertFalse(detect_validation_gate("NOx_balance", text)["satisfied"])


if __name__ == "__main__":
    unittest.main()
