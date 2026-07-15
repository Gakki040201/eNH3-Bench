from __future__ import annotations

import unittest

from enh3bench.evidence_linking import ORDERED_SOURCE_PROFILE, link_supporting_evidence


class OrderedEvidenceLinkingTests(unittest.TestCase):
    def test_real_paragraph_adjacency_drives_links_and_results_are_source_ordered(self) -> None:
        target = _record("S1", 2, 100, "Faradaic efficiency 20%.")
        adjacent = _record("S2", 3, 200, "15N isotope validation and Ar blank.")
        far = _record("S3", 20, 50, "Ammonia quantification by ion chromatography.")
        far["span_order"] = target["span_order"] = 1
        result = link_supporting_evidence(target, [target, adjacent, far], profile=ORDERED_SOURCE_PROFILE, minimum_link_score=0.60)
        self.assertEqual(result["validation"][0]["source_paragraph_distance"], 1)
        accepted = [item for role in ("validation", "quantification") for item in result[role]]
        self.assertEqual(accepted, sorted(accepted, key=lambda item: item["verified_source_start_offset"]))
        self.assertEqual(result["diagnostics"]["self_link_count"], 0)


def _record(span_id: str, paragraph: int, offset: int, text: str) -> dict[str, object]:
    return {"paper_id": "P1", "document_id": "P1", "source_span_id": span_id, "source_text": text, "paragraph_uid": f"PAR{paragraph}", "paragraph_global_index": paragraph, "section_uid": "SEC1", "source_order_key": f"{offset:06d}", "verified_source_start_offset": offset, "verified_source_end_offset": offset + len(text), "provenance_type": "body", "text_class": "primary_performance", "reaction_family": "eNRR", "is_primary_admissible": True}


if __name__ == "__main__":
    unittest.main()
