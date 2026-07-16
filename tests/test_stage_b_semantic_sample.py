from __future__ import annotations

import re
import unittest

from scripts.build_ordered_review_artifacts import (
    _artifact_diagnostics,
    _gas_purification_trap,
    _parallel_sample,
    _performance,
    _quantification,
    _semantic_closure_sample,
    _semantic_sentinel_sample,
    _validation,
)


class StageBSemanticSampleTests(unittest.TestCase):
    def test_fixed_seed_target_level_strata_and_quotas_are_deterministic(self) -> None:
        packets: list[dict[str, object]] = []
        packets.extend(_packets("eperf", 15, "eNRR", semantic="performance_result_claim", primary=True))
        packets.extend(_packets("eval", 15, "eNRR", semantic="validation_claim", primary=True))
        packets.extend(_packets("liperf", 15, "LiNRR", semantic="performance_result_claim", primary=True))
        packets.extend(_packets("n3perf", 15, "NO3RR", semantic="performance_result_claim", primary=True))
        packets.extend(_packets(
            "n3quant", 15, "NO3RR", semantic="ammonia_quantification_claim",
            primary=True, quantification=True,
        ))
        packets.extend(_packets("n2no", 10, "NO2RR", semantic="performance_result_claim", primary=True))
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
        self.assertEqual(first.count("- human_effective_reaction_family_correct:"), 130)
        self.assertEqual(first.count("- human_performance_result_evidence_correct:"), 130)
        self.assertEqual(first.count("- effective_reaction_family:"), 130)
        self.assertEqual(first.count("- performance_evidence_strength:"), 130)
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

        packet["semantic_claim_type"] = "performance_result_claim"
        packet["performance_result_evidence"] = True
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
            ("effective_reaction_family", "unclear"),
        ):
            with self.subTest(field=field):
                candidate = dict(packet)
                candidate[field] = value
                self.assertFalse(_gas_purification_trap(candidate))

    def test_semantic_sentinel_contains_twenty_passing_cases(self) -> None:
        p0090 = _packets(
            "p0090", 1, "NO3RR", semantic="performance_result_claim", primary=True,
        )[0]
        p0090.update({
            "paper_id": "P0090",
            "legacy_reaction_family": "eNRR",
            "document_reaction_family": "NO3RR",
            "effective_reaction_family": "NO3RR",
            "reaction_family_correction": True,
        })
        text, passed = _semantic_sentinel_sample([p0090])
        self.assertTrue(passed)
        self.assertEqual(text.count("\n## "), 20)
        self.assertEqual(text.count("- case_id: `SB_SENTINEL_"), 20)
        self.assertIn("P0090 nitrate family correction", text)
        self.assertIn("- Overall pass: `True`", text)

    def test_parallel_performance_group_requires_result_semantics(self) -> None:
        base = {
            "semantic_section_type": "results",
            "evidence_roles": ["performance"],
            "reaction_family": "LiNRR",
            "source_text_excerpt": "Faradaic efficiency was discussed.",
        }
        result = {
            **base, "paper_id": "P_RESULT", "source_span_id": "S_RESULT",
            "effective_reaction_family": "LiNRR", "semantic_claim_type": "performance_result_claim",
            "performance_result_evidence": True, "primary_semantic_eligibility": True,
        }
        context = {
            **base, "paper_id": "P_CONTEXT", "source_span_id": "S_CONTEXT",
            "effective_reaction_family": "LiNRR", "semantic_claim_type": "performance_context_claim",
            "performance_result_evidence": False, "primary_semantic_eligibility": True,
        }
        text = _parallel_sample([context, result])
        result_group = text.split("## LiNRR results/performance", 1)[1].split("\n## ", 1)[0]
        self.assertIn("P_RESULT", result_group)
        self.assertNotIn("P_CONTEXT", result_group)
        self.assertIn("semantic claim type: `performance_result_claim`", result_group)

    def test_artifact_diagnostics_detect_family_and_performance_mismatch(self) -> None:
        semantic_text = "\n".join((
            "# Sample",
            "## 1. eNRR performance",
            "- context_packet_id: `CP1`",
            "- paper_id: `P0090`",
            "- effective_reaction_family: `NO3RR`",
            "- semantic_claim_type: `performance_context_claim`",
            "- performance_result_evidence: `False`",
            "- human_notes:",
        ))
        sentinel_text = "\n".join((
            "# Sentinels",
            "## 1. Fixture",
            "- case_id: `SB_SENTINEL_01`",
            "- pass: `True`",
        ))
        diagnostics = _artifact_diagnostics(
            semantic_text,
            sentinel_text,
            "target semantic type may differ from linked validation role",
            [],
        )
        self.assertEqual(diagnostics["family_specific_primary_with_mismatched_effective_family_count"], 1)
        self.assertEqual(diagnostics["performance_context_primary_performance_strata_count"], 1)
        self.assertEqual(diagnostics["primary_performance_without_result_evidence_count"], 1)
        self.assertEqual(diagnostics["P0090_eNRR_sample_count"], 1)
        self.assertEqual(diagnostics["filled_human_review_field_count"], 0)


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
            "legacy_reaction_family": family,
            "document_reaction_family": family,
            "document_reaction_family_confidence": "high",
            "effective_reaction_family": family,
            "effective_reaction_family_source": "high_confidence_document",
            "reaction_family_correction": False,
            "document_target_reaction_family_conflict": False,
            "target_claim_type": legacy,
            "legacy_claim_type": legacy,
            "semantic_claim_type": semantic,
            "performance_evidence_strength": (
                "quantitative_result" if semantic == "performance_result_claim" else "none"
            ),
            "performance_evidence_signals": (
                ["numeric_value_with_unit"] if semantic == "performance_result_claim" else []
            ),
            "performance_result_evidence": semantic == "performance_result_claim",
            "quantitative_performance_evidence": semantic == "performance_result_claim",
            "target_ammonia_reaction_outcome_anchor": semantic == "performance_result_claim",
            "non_ammonia_reaction_activity": False,
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
            "structured_quantification_present": False,
            "structured_gate_text_conflict": False,
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
