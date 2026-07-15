from __future__ import annotations

import unittest

from scripts.build_ordered_review_artifacts import _semantic_closure_sample


class StageBSemanticSampleTests(unittest.TestCase):
    def test_fixed_seed_and_quotas_are_deterministic(self) -> None:
        packets: list[dict[str, object]] = []
        packets.extend(_packets("eperf", 15, "eNRR", claim="performance_claim", applicable=True))
        packets.extend(_packets("eval", 15, "eNRR", claim="validation_claim"))
        packets.extend(_packets("liperf", 15, "LiNRR", claim="performance_claim", applicable=True))
        packets.extend(_packets("limethod", 15, "LiNRR", text_class="protocol_guideline"))
        packets.extend(_packets("n3perf", 15, "NO3RR", claim="performance_claim", applicable=True))
        packets.extend(_packets("n3quant", 15, "NO3RR", quantification=True))
        packets.extend(_packets("n2no", 10, "NO2RR"))
        packets.extend(_packets("process", 10, "mixed", claim="process_claim", applicable=True))
        packets.extend(_packets("reference", 10, "eNRR", provenance="reference", text_class="reference_list"))
        packets[0]["previous_paragraph"] = {"text": "P" * 1000}
        packets[0]["target_paragraph"] = {"text": "T" * 1000}
        packets[0]["next_paragraph"] = {"text": "N" * 1000}
        packets[0]["evidence_items"] = [
            {"span_id": f"LINK_{index}", "text": "L" * 1000, "link_roles": ["validation"]}
            for index in range(5)
        ]

        first = _semantic_closure_sample(packets, seed=13)
        second = _semantic_closure_sample(list(reversed(packets)), seed=13)
        self.assertEqual(first, second)
        self.assertEqual(first.count("\n## "), 120)
        self.assertEqual(first.count("- human_section_type_correct:"), 120)
        self.assertTrue(first.startswith("# Stage B Semantic Closure Review Sample\n"))
        self.assertNotIn("P" * 601, first)
        self.assertNotIn("T" * 801, first)
        self.assertNotIn("N" * 601, first)
        self.assertNotIn("L" * 601, first)
        self.assertNotIn('"span_id": "LINK_4"', first)
        self.assertIn("结构对齐不代表科学可比性", first)


def _packets(
    prefix: str,
    count: int,
    family: str,
    *,
    claim: str = "",
    applicable: bool = False,
    provenance: str = "body",
    text_class: str = "unknown",
    quantification: bool = False,
) -> list[dict[str, object]]:
    records = []
    for index in range(count):
        span_id = f"{prefix}_{index:03d}"
        records.append({
            "context_packet_id": f"CP_{span_id}", "paper_id": f"P_{span_id}",
            "target_span_id": span_id, "target_reaction_family": family,
            "target_claim_type": claim, "packet_local_context_applicable": applicable,
            "target_provenance_type": provenance, "target_text_class": text_class,
            "family_gate_coverage": {
                "ammonia_quantification": {
                    "status": "observed_in_target" if quantification else "missing",
                    "supporting_span_ids": [span_id] if quantification else [],
                }
            },
            "evidence_items": [], "target_text": "fixture target",
        })
    return records


if __name__ == "__main__":
    unittest.main()
