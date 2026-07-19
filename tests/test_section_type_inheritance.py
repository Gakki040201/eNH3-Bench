from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from enh3bench.section_context import extract_markdown_section_blocks
from enh3bench.source_ledger import build_ordered_source_ledger, summarize_source_ledger


class SectionTypeInheritanceTests(unittest.TestCase):
    def _by_heading(self, markdown: str) -> dict[str, dict[str, object]]:
        return {
            str(block["raw_heading"]): block
            for block in extract_markdown_section_blocks(markdown)
            if block.get("raw_heading")
        }

    def test_standard_heading_is_direct(self) -> None:
        result = self._by_heading("## Results\n\nBody")["Results"]
        self.assertEqual(result["direct_section_type"], "results")
        self.assertEqual(result["effective_section_type"], "results")
        self.assertIsNone(result["inherited_section_type"])

    def test_unknown_child_inherits_results(self) -> None:
        child = self._by_heading("## Results\n### Catalyst characterization\nBody")["Catalyst characterization"]
        self.assertEqual(child["direct_section_type"], "unknown")
        self.assertEqual(child["inherited_section_type"], "results")
        self.assertEqual(child["effective_section_type"], "results")
        self.assertEqual(child["section_type"], child["effective_section_type"])

    def test_unknown_child_inherits_methods(self) -> None:
        child = self._by_heading("## Methods\n### Electrolyte preparation\nBody")["Electrolyte preparation"]
        self.assertEqual(child["effective_section_type"], "methods")

    def test_multilevel_child_tracks_semantic_distance(self) -> None:
        child = self._by_heading(
            "## Results and Discussion\n### Characterization\n#### Surface analysis\nBody"
        )["Surface analysis"]
        self.assertEqual(child["effective_section_type"], "results_and_discussion")
        self.assertEqual(child["inheritance_distance"], 2)
        self.assertEqual(child["inherited_from_source_section_index"], 0)

    def test_references_do_not_leak_to_following_same_level_heading(self) -> None:
        values = self._by_heading("## References\n### Cited works\n## Author notes\nBody")
        self.assertEqual(values["Cited works"]["effective_section_type"], "references")
        self.assertEqual(values["Author notes"]["effective_section_type"], "unknown")

    def test_supplementary_is_isolated_from_following_section(self) -> None:
        values = self._by_heading("## Supplementary Information\n### Extra data\n## Data availability\nBody")
        self.assertEqual(values["Extra data"]["effective_section_type"], "supplementary")
        self.assertEqual(values["Data availability"]["effective_section_type"], "unknown")

    def test_new_top_level_unknown_does_not_inherit_previous_peer(self) -> None:
        value = self._by_heading("# Results\n# Outlook\nBody")["Outlook"]
        self.assertEqual(value["effective_section_type"], "unknown")

    def test_heading_level_jump_remains_unknown_with_warning(self) -> None:
        value = self._by_heading("## Results\n#### Abrupt child\nBody")["Abrupt child"]
        self.assertEqual(value["effective_section_type"], "unknown")
        self.assertIn("section_inheritance_unresolved", value["section_inheritance_warnings"])

    def test_title_and_abstract_do_not_propagate(self) -> None:
        values = self._by_heading("# Paper title\n## Scope\n# Abstract\n## Motivation\nBody")
        self.assertEqual(values["Scope"]["effective_section_type"], "unknown")
        self.assertEqual(values["Motivation"]["effective_section_type"], "unknown")

    def test_source_ledger_resolves_inherited_uid_and_layered_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text(
                "## Results\n### Characterization\n#### Surface analysis\nBody", encoding="utf-8"
            )
            ledger = build_ordered_source_ledger(root)
            sections = ledger.sections_by_document["P1"]
            parent = next(item for item in sections if item["raw_heading"] == "Results")
            child = next(item for item in sections if item["raw_heading"] == "Surface analysis")
            self.assertEqual(child["inherited_from_section_uid"], parent["section_uid"])
            self.assertEqual(child["section_type"], child["effective_section_type"])
            summary = summarize_source_ledger(ledger, [])
            self.assertEqual(summary["direct_unknown_count"], 2)
            self.assertEqual(summary["effective_unknown_count"], 0)
            self.assertEqual(summary["inherited_section_count"], 2)
            self.assertEqual(summary["inheritance_distance_distribution"], {"1": 1, "2": 1})


if __name__ == "__main__":
    unittest.main()
