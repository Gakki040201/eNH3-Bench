from __future__ import annotations

import unittest

from enh3bench.reaction_profiles import aggregate_paper_reaction_family, propagate_paper_family_to_unclear_spans


class ReactionFamilyPaperConsensusTests(unittest.TestCase):
    def test_reference_list_title_does_not_set_paper_family(self) -> None:
        consensus = aggregate_paper_reaction_family(
            [
                {
                    "paper_id": "P1",
                    "source_span_id": "R1",
                    "provenance_type": "reference",
                    "source_text": "Lithium-mediated nitrogen reduction to ammonia. Journal title.",
                }
            ]
        )
        self.assertEqual(consensus["reaction_family"], "unclear")

    def test_high_confidence_explicit_span_not_overwritten_by_consensus(self) -> None:
        records = [
            {
                "paper_id": "P1",
                "source_span_id": "S1",
                "provenance_type": "abstract",
                "is_primary_admissible": True,
                "source_text": "N2-to-NH3 electrochemical nitrogen reduction was studied.",
            },
            {
                "paper_id": "P1",
                "source_span_id": "S2",
                "provenance_type": "results",
                "is_primary_admissible": True,
                "source_text": "Nitrate was the reactant and nitrate-to-ammonia FE was measured.",
                "reaction_family": "NO3RR",
                "reaction_family_confidence": "high",
                "reaction_family_scope": "explicit_span",
            },
        ]
        propagated = propagate_paper_family_to_unclear_spans(records)
        explicit = [record for record in propagated if record["source_span_id"] == "S2"][0]
        self.assertEqual(explicit["reaction_family"], "NO3RR")
        self.assertTrue(explicit["reaction_family_conflict"])

    def test_unclear_low_information_span_inherits_paper_family(self) -> None:
        records = [
            {
                "paper_id": "P1",
                "source_span_id": "S1",
                "provenance_type": "abstract",
                "is_primary_admissible": True,
                "source_text": "N2-to-NH3 electrochemical nitrogen reduction was confirmed with 15N2.",
            },
            {
                "paper_id": "P1",
                "source_span_id": "S2",
                "provenance_type": "body",
                "is_primary_admissible": True,
                "source_text": "The catalyst performance was stable over the test.",
            },
        ]
        propagated = propagate_paper_family_to_unclear_spans(records)
        inherited = [record for record in propagated if record["source_span_id"] == "S2"][0]
        self.assertEqual(inherited["reaction_family"], "eNRR")
        self.assertEqual(inherited["reaction_family_scope"], "paper_consensus")
        self.assertEqual(inherited["paper_level_reaction_family"], "eNRR")


if __name__ == "__main__":
    unittest.main()
