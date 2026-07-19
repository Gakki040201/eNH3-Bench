from __future__ import annotations

import unittest

from enh3bench.evidence_linking import classify_link_type, link_supporting_evidence, score_link


class EvidenceLinkingTests(unittest.TestCase):
    def test_classification_signals(self) -> None:
        cases = {
            "Faradaic efficiency and NH3 yield": "performance",
            "15N isotope and Ar blank": "validation",
            "ion chromatography calibration": "quantification",
            "flow cell GDE outlet wetting": "reactor",
            "capture separation and electrolyte recycle": "process",
            "false positive background ammonia": "negative_or_contradicting",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify_link_type(_record("S2", text)), expected)

    def test_score_prefers_same_section_and_primary_provenance(self) -> None:
        target = _record("P1_S010", "FE 20%", section="Results")
        close = _record("P1_S011", "15N isotope", section="Results")
        far = {**_record("P1_S099", "15N isotope", section="Methods"), "is_primary_admissible": False}
        self.assertGreater(score_link(target, close), score_link(target, far))

    def test_category_and_total_limits(self) -> None:
        target = _record("P1_S001", "Target FE 20%")
        records = [target] + [_record(f"P1_S00{i}", "15N isotope validation") for i in range(2, 6)]
        result = link_supporting_evidence(target, records, {"maximum_per_category": 2, "maximum_total_links": 1})
        self.assertEqual(result["total_links"], 1)
        self.assertLessEqual(len(result["validation"]), 1)


def _record(span_id: str, text: str, section: str = "Results") -> dict[str, object]:
    return {"paper_id": "P1", "source_span_id": span_id, "source_text": text, "section_path": [section], "provenance_type": "body", "text_class": "primary_performance", "is_primary_admissible": True, "reaction_family": "eNRR"}


if __name__ == "__main__":
    unittest.main()
