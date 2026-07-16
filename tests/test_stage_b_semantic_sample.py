from __future__ import annotations

import re
import unittest

from scripts.build_ordered_review_artifacts import (
    _gas_purification_trap,
    _performance,
    _quantification,
    _semantic_closure_sample,
    _validation,
)


class StageBSemanticSampleTests(unittest.TestCase):
    def test_fixed_seed_target_level_strata_and_quotas_are_deterministic(self) -> None:
        packets: list[dict[str, object]] = []
        packets.extend(_packets("eperf", 15, "eNRR", semantic="performance_claim", primary=True))
        packets.extend(_packets("eval", 15, "eNRR", semantic="validation_claim", primary=True))
        packets.extend(_packets("liperf", 15, "LiNRR", semantic="performance_claim", primary=True))
        packets.extend(_packets("n3perf", 15, "NO3RR", semantic="performance_claim", primary=True))
        packets.extend(_packets(
            "n3quant", 15, "NO3RR", semantic="ammonia_quantification_claim",
            primary=True, quantification=True,
        ))
        packets.extend(_packets("n2no", 10, "NO2RR", semantic="performance_claim", primary=True))
        packets.extend(_packets("process", 10, "mixed", semantic="process_claim", primary=True))
        packets.extend(_packets(
            "trap", 7, "eNRR", semantic="gas_purification_or_capture_claim", gas_trap=True,
            target_text="The gas passed through an acid trap for ammonia removal.",
        ))
        packets.extend(_packets("review", 6, "eNRR", semantic="mechanism_claim", document_genre="review"))
        packets.extend(_packets(
            "external", 6, "eNRR", semantic="performance_claim",
            span_scope="external_or_cited_work", ownership="external_or_cited_authors",
        ))
        packets.extend(_packets(
            "background", 4, "eNRR", semantic="secondary_context_claim",
            span_scope="background_or_review", ownership="general_literature",
        ))
        packets.extend(_packets(
            "legacy", 4, "eNRR", semantic="mechanism_claim", legacy="process_claim", conflict=True,
        ))
        packets.extend(_packets(
            "offtarget", 4, "eNRR", semantic="performance_claim", off_target=True,
            target_text="CO2RR Faradaic efficiency in a Zn-air battery was reported.",
        ))
        packets.extend(_packets(
            "false_negative", 4, "eNRR", semantic="untyped_claim",
            target_text="Ammonia was measured with a candidate selective electrode assay.",
        ))
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
        self.assertEqual(first.count("\n## "), 130)
        self.assertEqual(first.count("- human_section_type_correct:"), 130)
        self.assertEqual(first.count("- human_document_genre_correct:"), 130)
        self.assertEqual(first.count("- human_span_claim_scope_correct:"), 130)
        self.assertEqual(first.count("- human_document_scope_correct:"), 130)
        self.assertEqual(first.count("- human_quantification_vs_trap_correct:"), 130)
        self.assertEqual(first.count("- context_packet_id:"), 130)
        self.assertEqual(first.count("- sample_stratum_type:"), 130)
        self.assertEqual(first.count("- hard_gate_failures:"), 130)
        context_ids = re.findall(r"(?m)^- context_packet_id: `([^`]+)`$", first)
        self.assertEqual(len(context_ids), len(set(context_ids)))
        self.assertTrue(first.startswith("# Stage B Semantic Closure Review Sample\n"))
        self.assertIn("- Requested gas-trap quota: 10", first)
        self.assertIn("- Unique target-level gas-trap records available: 7", first)
        self.assertIn("- Gas-trap records sampled: 7", first)
        self.assertIn("- No duplicate or synthetic gas-trap samples were added.", first)
        self.assertNotIn("P" * 601, first)
        self.assertNotIn("T" * 801, first)
        self.assertNotIn("N" * 601, first)
        self.assertNotIn("L" * 601, first)
        self.assertNotIn('"span_id": "LINK_4"', first)
        self.assertIn("结构对齐不代表科学可比性。", first)
        self.assertEqual(
            len(
                re.findall(
                    r"(?m)^## \d+\. gas-purification trap \(target-only, not quantification\)$",
                    first,
                )
            ),
            7,
        )
        gas_sections = [
            section for section in first.split("\n## ")
            if section.splitlines()[0].endswith("gas-purification trap (target-only, not quantification)")
        ]
        self.assertEqual(len(gas_sections), 7)
        self.assertTrue(all("- gas_purification_trap_signal: `True`" in section for section in gas_sections))
        self.assertTrue(all("- ammonia_quantification_signal: `False`" in section for section in gas_sections))
        sample_sections = [section for section in first.split("\n## ") if re.match(r"\d+\. ", section)]
        primary_sections = [section for section in sample_sections if "- sample_stratum_type: `primary`" in section]
        secondary_sections = [section for section in sample_sections if "- sample_stratum_type: `secondary`" in section]
        self.assertTrue(all("- primary_semantic_eligibility: `True`" in section for section in primary_sections))
        self.assertTrue(all(
            "- primary_semantic_eligibility: `False`" in section
            or not re.search(r"- secondary_stratum_reason: `(?:not_applicable)?`", section)
            for section in secondary_sections
        ))

    def test_primary_predicates_ignore_legacy_and_linked_packet_signals(self) -> None:
        packet = _packets(
            "predicate", 1, "eNRR", semantic="validation_claim", legacy="performance_claim", primary=True,
        )[0]
        packet["evidence_role_index"] = {"validation": []}
        self.assertFalse(_performance(packet))
        self.assertTrue(_validation(packet))

        packet["semantic_claim_type"] = "performance_claim"
        packet["ammonia_quantification_signal"] = False
        packet["family_gate_coverage_primary_admissible"] = {
            "ammonia_quantification": {"status": "observed_in_linked_evidence"}
        }
        self.assertFalse(_quantification(packet))

    def test_gas_trap_predicate_uses_target_flags_only(self) -> None:
        packet = _packets(
            "trap_neighbor", 1, "eNRR", semantic="gas_purification_or_capture_claim",
        )[0]
        packet["previous_paragraph"] = {"text": "Gas passed through an acid trap."}
        packet["evidence_items"] = [{"text": "A base trap scrubbed ammonia."}]
        self.assertFalse(_gas_purification_trap(packet))

        packet["gas_purification_trap_signal"] = True
        packet["target_text"] = "The outlet ammonia was captured in an acid trap."
        self.assertTrue(_gas_purification_trap(packet))

        packet["target_text"] = "We did not use a downstream acid trap for ammonia."
        self.assertFalse(_gas_purification_trap(packet))

        packet["target_text"] = "The outlet gas passed through a cold trap."
        self.assertFalse(_gas_purification_trap(packet))

    def test_gas_trap_sample_requires_target_document_semantics(self) -> None:
        packet = _packets(
            "trap_scope", 1, "eNRR", semantic="gas_purification_or_capture_claim",
            gas_trap=True, target_text="The outlet ammonia was captured in an acid trap.",
        )[0]
        for field, value in (
            ("document_genre", "review"),
            ("span_claim_scope", "external_or_cited_work"),
            ("claim_ownership", "external_or_cited_authors"),
            ("semantic_claim_type", "secondary_context_claim"),
            ("target_reaction_family", "unclear"),
        ):
            with self.subTest(field=field):
                candidate = dict(packet)
                candidate[field] = value
                self.assertFalse(_gas_purification_trap(candidate))


def _packets(
    prefix: str,
    count: int,
    family: str,
    *,
    semantic: str,
    legacy: str = "",
    primary: bool = False,
    document_genre: str = "primary_research",
    span_scope: str = "target_document",
    ownership: str = "target_authors",
    quantification: bool = False,
    gas_trap: bool = False,
    conflict: bool = False,
    off_target: bool = False,
    target_text: str = "fixture target",
) -> list[dict[str, object]]:
    records = []
    for index in range(count):
        span_id = f"{prefix}_{index:03d}"
        records.append({
            "context_packet_id": f"CP_{span_id}",
            "paper_id": f"P_{span_id}",
            "target_span_id": span_id,
            "target_reaction_family": family,
            "target_claim_type": legacy,
            "legacy_claim_type": legacy,
            "semantic_claim_type": semantic,
            "semantic_claim_type_confidence": "high",
            "semantic_claim_type_conflict": conflict,
            "document_genre": document_genre,
            "span_claim_scope": span_scope,
            "document_scope": span_scope,
            "claim_ownership": ownership,
            "primary_semantic_eligibility": primary,
            "packet_local_context_applicable": primary,
            "target_provenance_type": "body",
            "target_text_class": "primary_performance",
            "ammonia_quantification_signal": quantification,
            "gas_purification_trap_signal": gas_trap,
            "mass_spectrometry_quantification_signal": False,
            "enzymatic_quantification_signal": False,
            "local_off_target_reaction_conflict": off_target,
            "family_gate_coverage": {},
            "family_gate_coverage_primary_admissible": {},
            "evidence_items": [],
            "target_text": target_text,
        })
    return records


if __name__ == "__main__":
    unittest.main()
