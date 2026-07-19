from __future__ import annotations

import unittest

from enh3bench.audit_routing import select_reference_spans_for_audit
from enh3bench.human_audit import merge_audit_sources


class ReferenceSamplingTests(unittest.TestCase):
    def test_sampling_is_reproducible_for_same_seed(self) -> None:
        records = [_record("P1", f"S{i}") for i in range(20)]
        first = select_reference_spans_for_audit(records, seed="fixed", sample_rate=0.5, max_per_paper=1)
        second = select_reference_spans_for_audit(list(reversed(records)), seed="fixed", sample_rate=0.5, max_per_paper=1)
        self.assertEqual(first, second)

    def test_at_most_one_ordinary_reference_per_paper(self) -> None:
        records = [_record("P1", f"P1-S{i}") for i in range(8)] + [_record("P2", f"P2-S{i}") for i in range(8)]
        selected = select_reference_spans_for_audit(records, seed="fixed", sample_rate=1.0, max_per_paper=1)
        selected_records = [record for record in records if record["source_span_id"] in selected]
        self.assertEqual(len(selected_records), 2)
        self.assertEqual({record["paper_id"] for record in selected_records}, {"P1", "P2"})

    def test_conflicts_are_reviewed_outside_ordinary_cap(self) -> None:
        records = [
            _record("P1", "ordinary-1"),
            _record("P1", "ordinary-2"),
            {**_record("P1", "conflict-1"), "reaction_family_conflict": True},
            {**_record("P1", "conflict-2"), "force_human_review": True},
        ]
        merged = merge_audit_sources(
            records,
            routing_profile="secondary_hardening_v1",
            reference_audit_sample_rate=1.0,
            max_reference_spans_per_paper_for_audit=1,
            reference_audit_seed="fixed",
        )
        ordinary_sampled = [record for record in merged if record["reference_sampled_for_audit"]]
        conflicts = [record for record in merged if record["reference_conflict_review"]]
        self.assertEqual(len(ordinary_sampled), 1)
        self.assertEqual(len(conflicts), 2)
        self.assertTrue(all(record["overall_needs_human_review"] for record in conflicts))

    def test_references_are_retained_after_sampling(self) -> None:
        records = [_record("P1", f"S{i}") for i in range(5)]
        merged = merge_audit_sources(
            records,
            routing_profile="secondary_hardening_v1",
            reference_audit_sample_rate=1.0,
            reference_audit_seed="fixed",
        )
        self.assertEqual(len(merged), len(records))
        self.assertEqual({record["source_span_id"] for record in merged}, {record["source_span_id"] for record in records})


def _record(paper_id: str, source_span_id: str) -> dict[str, object]:
    return {
        "paper_id": paper_id,
        "source_span_id": source_span_id,
        "evidence_id": f"E-{source_span_id}",
        "source_text": "1. Smith et al. A citation. Journal (2020).",
        "provenance_type": "reference",
        "text_class": "reference_list",
        "maximum_supported_boundary": "unsupported_or_secondary",
        "admissibility_status": "reject_or_low_trust_provenance",
        "validation_gates": {},
        "missing_boundary_fields": [],
        "required_controls": [],
        "reaction_family_conflict": False,
        "text_class_provenance_conflict": False,
        "boundary_agreement": True,
    }


if __name__ == "__main__":
    unittest.main()
