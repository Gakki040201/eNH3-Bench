from __future__ import annotations

import unittest

from enh3bench.provenance_rules import (
    infer_provenance_from_text,
    is_primary_admissible,
    is_reject_or_low_trust,
    is_secondary_or_context,
    normalize_provenance_type,
)


class ProvenanceRulesTests(unittest.TestCase):
    def test_yaml_like_front_matter_is_low_trust(self) -> None:
        result = infer_provenance_from_text(
            "---\nsource_file: input_raw\\paper.pdf\nconversion_method: docling\nhuman_verification_required: true\n---",
            raw_record={"span_id": "paper_S001"},
        )
        self.assertIn(result["provenance_type"], {"front_matter", "metadata"})
        self.assertTrue(result["is_reject_or_low_trust"])

    def test_reference_list_is_reference_or_bibliography(self) -> None:
        result = infer_provenance_from_text(
            "[1] Smith et al. Journal 12, 44-50 (2020). doi:10.1000/test\n"
            "[2] Chen et al. Catalysis 9, 12-18 (2021). doi:10.1000/test2\n"
            "[3] Wang et al. Science 10, 20-30 (2022).",
            section="References",
        )
        self.assertIn(result["provenance_type"], {"reference", "bibliography"})
        self.assertTrue(result["is_reject_or_low_trust"])

    def test_markdown_review_table(self) -> None:
        result = infer_provenance_from_text(
            "| Reference | Catalyst | Electrolyte | FE (%) | 15N |\n"
            "|---|---|---|---|---|\n"
            "| Smith et al. (2020) | Fe | KOH | 10 | no |\n"
            "| Chen et al. (2021) | Ru | KOH | 11 | yes |\n"
            "| Wang et al. (2022) | Au | KOH | 12 | no |",
        )
        self.assertEqual(result["provenance_type"], "review_table")
        self.assertTrue(result["is_secondary_or_context"])

    def test_figure_caption(self) -> None:
        result = infer_provenance_from_text("Fig. 2. NH3 yield and FE of the catalyst at different potentials.")
        self.assertEqual(result["provenance_type"], "figure_caption")
        self.assertTrue(result["is_secondary_or_context"])

    def test_body_results_section(self) -> None:
        result = infer_provenance_from_text(
            "The catalyst produced NH3 with 15N2 validation, FE, yield, current density, and voltage.",
            section="Results and discussion",
        )
        self.assertIn(result["provenance_type"], {"results", "discussion"})
        self.assertTrue(result["is_primary_admissible"])

    def test_normalize_and_group_helpers(self) -> None:
        self.assertEqual(normalize_provenance_type("Figure"), "figure_caption")
        self.assertTrue(is_primary_admissible("results"))
        self.assertTrue(is_secondary_or_context("table"))
        self.assertTrue(is_reject_or_low_trust("metadata"))


if __name__ == "__main__":
    unittest.main()
