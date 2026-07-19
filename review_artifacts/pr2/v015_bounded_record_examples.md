# v0.15 Bounded Record Examples

## Method and boundary

These ten examples are deterministic projections from `data/cleanroom/enrr_cleanroom_v015_20260718/`. Records were sorted by the named ID and the first record satisfying the stated condition was selected. Fields not material to the review question are omitted; emitted values are not relabeled. Every displayed source-text value is a **bounded excerpt** of at most 600 characters, and truncation is marked. No absolute runtime path, full document, or completed human label is included.

## 1. DocumentRecord

Selection: first record after sorting `document_ledger.jsonl` by `document_id`.

```json
{
  "document_assessment_call_count": 1,
  "document_body_sha256": "7b9103cc6c6ad6e5c27151309cc1fe2f7edd3a6496392130752909a9037bb851",
  "document_character_count": 64400,
  "document_genre": "perspective",
  "document_genre_confidence": "high",
  "document_id": "P0004_Choi_2020_Identification_and_elimination_of_false_positives_in_electrochemical_nitrogen_reduction_studies",
  "document_reaction_family": "eNRR",
  "document_reaction_family_confidence": "medium",
  "document_reaction_family_conflict": false,
  "document_ref": "input_markdown/P0004_Choi_2020_Identification_and_elimination_of_false_positives_in_electrochemical_nitrogen_reduction_studies.md",
  "paper_id": "P0004_Choi_2020_Identification_and_elimination_of_false_positives_in_electrochemical_nitrogen_reduction_studies",
  "paragraph_count": 116,
  "pipeline_profile": "document_first_cleanroom_v1",
  "record_created_by_stage": "documents",
  "run_name": "enrr_cleanroom_v015_20260718",
  "schema_version": "0.15-cleanroom.1",
  "section_count": 15
}
```

- What it supports: the run emits one explicit schema/profile document assessment with a body hash, structure counts, and one cached assessment call.
- What it does not support: correctness of the `perspective` or `eNRR` labels.
- Review risk: document genre/family errors propagate into provenance ceilings and primary eligibility.

## 2. SourceNodeRecord

Selection: first record after sorting `source_nodes.jsonl` by `source_node_id`. `source_text` is a **bounded excerpt**.

```json
{
  "direct_section_type": "unknown",
  "document_id": "P0105_Liu_2024_Efficient_ammonia_synthesis_from_the_air_using_tandem_non-thermal_plasma_and_electrocatalysis_at_ambient",
  "document_region": "main_body",
  "effective_section_type": "unknown",
  "maximum_support_role": "primary_support",
  "paper_id": "P0105_Liu_2024_Efficient_ammonia_synthesis_from_the_air_using_tandem_non-thermal_plasma_and_electrocatalysis_at_ambient",
  "paragraph_uid": "PAR_051c2039559a48bd2fb987dff190c6032e1e2a93226b0c5754539b9161fafc73",
  "provenance_type": "primary_body",
  "raw_heading": "Evaluation of the performance of air-to-NH3 conversion in the pNOR-eNOx -RR tandem system",
  "section_uid": "SEC_864d7462d3512394cf8a36c50e6a529c07b3cbf4680ccf6fa8c5bfb0b4aa9697",
  "source_end_offset": 31432,
  "source_locator": "P0105_Liu_2024_Efficient_ammonia_synthesis_from_the_air_using_tandem_non-thermal_plasma_and_electrocatalysis_at_ambient::SEC007::PAR008",
  "source_node_id": "CRN15_000589204C0215F20478",
  "source_start_offset": 30472,
  "source_text": "con fi rming that N2 in the air is the N source. We then performed batch experiments to investigate the impact of the spark discharge time on the NH3 yield rate and corresponding FE (Supplementary Fig. 54). The solutions with different spark discharge time were applied as the afterward electrolyte. As shown in Fig. 5b, the NH3 yield increases rapidly as the discharge time increases from 10 to 30 min. Further expanding the discharge time to 120 min only leads to a small increment of NH3 yield rat[bounded excerpt truncated]",
  "source_text_sha256": "83a92ffe4ad7d2b149bb436513ed7aef9a71549f2824b5dd28655180badd4817"
}
```

- What it supports: the node has a stable ID, exact offsets, logical locator, text hash, and explicit provenance ceiling.
- What it does not support: that the excerpt alone proves a complete paper-level performance claim.
- Review risk: `unknown` section typing and excerpt boundaries may require neighboring context.

## 3. CandidateSpanRecord

Selection: first record after sorting `candidate_spans.jsonl` by `cleanroom_span_id`. `source_text` is a **bounded excerpt**.

```json
{
  "candidate_kind": "performance_signal",
  "candidate_priority": 3,
  "candidate_score": 0.55,
  "cleanroom_span_id": "CR15_0018066159D50234C358",
  "document_id": "P0250_Ji_2023_Identification_of_Dynamic_Active_Sites_Among_Cu_Species_Derived_from_MOFs_CuPc_for_Electrocatalytic_Nitra",
  "generation_method": "bounded_sentence_window",
  "legacy_source_span_id": "",
  "maximum_support_role": "context_only",
  "paper_id": "P0250_Ji_2023_Identification_of_Dynamic_Active_Sites_Among_Cu_Species_Derived_from_MOFs_CuPc_for_Electrocatalytic_Nitra",
  "provenance_type": "reference",
  "source_end_offset": 41511,
  "source_locator": "P0250_Ji_2023_Identification_of_Dynamic_Active_Sites_Among_Cu_Species_Derived_from_MOFs_CuPc_for_Electrocatalytic_Nitra::SEC017::PAR004::CRANCHOR:38524-41511",
  "source_node_id": "CRN15_8EA0807ACB3CB772F8E4",
  "source_start_offset": 38524,
  "source_text": "8. H. Xu, Y.Y. Ma, J. Chen, W.X. Zhang, J.P. Yang, Electrocatalytic reduction of nitrate-a step towards a sustainable nitrogen cycle. Chem. Soc. Rev. 51 (7), 2710-2758 (2022). 9. R. Zhang, Y. Guo, S.C. Zhang, D. Chen, Y.W. Zhao et al., Efficient ammonia electrosynthesis and energy conversion through a Zn-nitrate battery by iron doping engineered nickel phosphide catalyst. Adv. Energy Mater. 12 (13), 2103872 (2022).[bounded excerpt truncated]",
  "source_text_sha256": "df5ebe934cc9d2b4c39e77ea3471499c791fd4829666d0ed9806fd1d0ae84a72",
  "trigger_signals": [
    "performance_signal",
    "general_ammonia_context"
  ]
}
```

- What it supports: recall-oriented candidate generation retains a reference-list hit while explicitly capping it at `context_only`.
- What it does not support: primary evidence, claim ownership, or semantic correctness.
- Review risk: trigger terms inside citations can look result-bearing without provenance controls.

## 4. Primary-eligible SemanticSpanRecord

Selection: first record by `cleanroom_span_id` where `primary_semantic_eligibility` is true. `source_text` is a **bounded excerpt**. The gate object is a projection of selected emitted gates.

```json
{
  "ammonia_quantification_signal": false,
  "claim_ownership": "target_authors",
  "cleanroom_span_id": "CR15_00185946255E6515E643",
  "document_genre": "primary_research",
  "document_id": "P0202_Ko_2020_The_impact_of_nitrogen_oxides_on_electrochemical_carbon_dioxide_reduction",
  "document_reaction_family": "unclear",
  "document_scope": "target_document",
  "effective_reaction_family": "NORR",
  "effective_reaction_family_source": "explicit_high_confidence_target_span",
  "gas_purification_trap_signal": false,
  "hard_gate_failures": [],
  "needs_review": false,
  "needs_review_reasons": [],
  "paper_id": "P0202_Ko_2020_The_impact_of_nitrogen_oxides_on_electrochemical_carbon_dioxide_reduction",
  "performance_result_evidence": true,
  "primary_semantic_eligibility": true,
  "quantitative_performance_evidence": false,
  "semantic_claim_type": "mechanism_claim",
  "semantic_claim_type_confidence": "medium",
  "semantic_outcome": "primary_eligible",
  "source_end_offset": 10119,
  "source_locator": "P0202_Ko_2020_The_impact_of_nitrogen_oxides_on_electrochemical_carbon_dioxide_reduction::SEC003::PAR004::CRANCHOR:8429-10119",
  "source_start_offset": 8429,
  "source_text": "When 0.83% NO was introduced at t = 0.5 h, the total CO2RR FE decreased noticeably on all three catalysts (Fig. 2a-c). On average, the losses in CO2RR FE accounted for 33.9, 29.6, and 27.9% on Cu, Ag, and Sn, respectively (Fig. 2d), which is likely due to the preferential reduction of NO over CO2. Assuming NO is fully converted to NH3, conversions of NO during CO2RR are between 48% and 60% (Supplementary Table 5). As shown in Fig. 1b, the standard potentials of NORR are much more positive than[bounded excerpt truncated]",
  "span_claim_scope": "target_document",
  "target_ammonia_reaction_outcome_anchor": true,
  "validation_gate_decisions": {
    "NO_source_defined": {
      "gate_conflict": false,
      "gate_detection_signals": [
        "target_text_NO_source_defined"
      ],
      "gate_detection_source": "target_text",
      "satisfied": true
    },
    "ammonia_quantification": {
      "gate_conflict": false,
      "gate_detection_signals": [],
      "gate_detection_source": "",
      "satisfied": false
    }
  }
}
```

- What it supports: at least one real record passes the implemented hard gates with stable source grounding and an explicit local NORR family.
- What it does not support: human correctness, quantitative performance validity, causality, or paper-level admissibility.
- Review risk: the excerpt contains an assumption about full conversion; human review must distinguish mechanism/context from measured ammonia performance.

## 5. Needs-review SemanticSpanRecord

Selection: first record by `cleanroom_span_id` where `needs_review` is true. `source_text` is a **bounded excerpt**.

```json
{
  "ammonia_quantification_signal": false,
  "claim_ownership": "unclear",
  "cleanroom_span_id": "CR15_003204D915561B1BB0E6",
  "document_genre": "primary_research",
  "document_id": "P0413_Li_2025_Stabilizing_Cu0-Cuδ_sites_via_ohmic_contact_interface_engineering_for_ampere-level_nitrate_electroreducti",
  "document_reaction_family": "NO3RR",
  "document_scope": "unclear",
  "effective_reaction_family": "NO3RR",
  "effective_reaction_family_source": "explicit_high_confidence_target_span",
  "hard_gate_failures": [
    "claim_ownership_not_target_authors",
    "document_scope_not_target_document",
    "provenance_not_primary_admissible",
    "semantic_type_not_primary_supporting",
    "span_scope_not_target_document"
  ],
  "needs_review": true,
  "needs_review_reasons": [
    "claim_ownership_unclear",
    "span_claim_scope_unclear"
  ],
  "paper_id": "P0413_Li_2025_Stabilizing_Cu0-Cuδ_sites_via_ohmic_contact_interface_engineering_for_ampere-level_nitrate_electroreducti",
  "performance_result_evidence": false,
  "primary_semantic_eligibility": false,
  "quantitative_performance_evidence": false,
  "semantic_claim_type": "performance_context_claim",
  "semantic_claim_type_confidence": "medium",
  "semantic_outcome": "secondary_context",
  "semantic_warnings": [
    "context_only_source"
  ],
  "source_end_offset": 41183,
  "source_locator": "P0413_Li_2025_Stabilizing_Cu0-Cuδ_sites_via_ohmic_contact_interface_engineering_for_ampere-level_nitrate_electroreducti::SEC008::PAR003::CRANCHOR:40788-41183",
  "source_start_offset": 40788,
  "source_text": "Fig. 6 | Electrochemical NO3RR with actual industrial current density coupled with OER Reaction in a two-electrode system. a, b Scheme and digital photo of the electrolyzer coupling NO3RR with OER. c The LSV curves of overall water splitting systems and NO3RR//OER paired-electrolysis system (scan rate 100 mV s-1 in 1 M KOH with/without 1 M NO3-). d Stability measurement of NO3RR//OER paired-",
  "span_claim_scope": "unclear",
  "target_ammonia_reaction_outcome_anchor": false
}
```

- What it supports: caption/context uncertainty is explicit, explainable, and fail-closed for primary eligibility.
- What it does not support: a completed human finding that the span is wrong.
- Review risk: captions can summarize genuine results, but they cannot become primary positive support under the v0.15 contract.

## 6. EvidenceLinkRecord

Selection: first record after sorting `evidence_links.jsonl` by `evidence_link_id`.

```json
{
  "evidence_cleanroom_span_id": "CR15_4EB63C166A9E56C6685C",
  "evidence_link_id": "CRL15_000B2D4C6DCE80469601",
  "is_context_only": false,
  "link_roles": [
    "gas_handling_context"
  ],
  "link_score": 0.4338,
  "link_signals": [
    "same_paper",
    "bounded_source_distance",
    "gas_handling_context"
  ],
  "link_warnings": [
    "link_does_not_upgrade_ownership_or_provenance"
  ],
  "paper_id": "P0272_Li_2024_Lattice_hydrogen_transfer_in_titanium_hydride_enhances_electrocatalytic_nitrate_to_ammonia_conversion",
  "pipeline_profile": "document_first_cleanroom_v1",
  "record_created_by_stage": "links",
  "run_name": "enrr_cleanroom_v015_20260718",
  "schema_version": "0.15-cleanroom.1",
  "source_eligibility": "primary_admissible",
  "target_cleanroom_span_id": "CR15_752308A7DBC4FADDC25C"
}
```

- What it supports: the endpoints are paper-scoped, distinct, stable, and assigned a bounded association role.
- What it does not support: causality, sufficiency, or an ownership/provenance upgrade.
- Review risk: a proximity score can be overread as semantic confidence.

## 7. PaperRecord

Selection: first record after sorting `paper_records.jsonl` by `paper_id`.

```json
{
  "best_evidence_span_ids": [],
  "candidate_span_count": 76,
  "document_conflicts": [],
  "document_genre": "perspective",
  "document_id": "P0004_Choi_2020_Identification_and_elimination_of_false_positives_in_electrochemical_nitrogen_reduction_studies",
  "document_reaction_family": "eNRR",
  "evidence_link_count": 36,
  "paper_admissibility_reasons": [
    "critical_conflict_or_uncertainty"
  ],
  "paper_admissibility_status": "needs_review",
  "paper_id": "P0004_Choi_2020_Identification_and_elimination_of_false_positives_in_electrochemical_nitrogen_reduction_studies",
  "paper_warnings": [
    "paper_level_record_is_limited_aggregation",
    "scientific_comparability_not_established"
  ],
  "performance_summary": {
    "primary_result_span_count": 0,
    "quantitative_result_span_count": 0
  },
  "primary_claim_counts": {},
  "primary_eligible_span_count": 0,
  "quantification_summary": {
    "primary_quantification_span_count": 0,
    "trap_only_span_count": 6
  },
  "record_created_by_stage": "papers",
  "review_priority": "high",
  "secondary_context_count": 76,
  "semantic_span_count": 76
}
```

- What it supports: primary and secondary counts are separated and the conservative status is explained.
- What it does not support: a human judgment about paper quality or scientific validity.
- Review risk: `needs_review` can be misread as rejection rather than unresolved automated aggregation.

## 8. No-candidate fallback / distinct needs-review PaperRecord

Selection: the real run contains **zero** no-candidate PaperRecords. Per the allowed fallback, this is the first distinct record by `paper_id` whose status is `needs_review` or `insufficient_evidence`.

```json
{
  "best_evidence_span_ids": [
    "CR15_32DDDB28076BBF655FEC"
  ],
  "candidate_span_count": 15,
  "document_conflicts": [],
  "document_genre": "primary_research",
  "document_id": "P0006_Choi_2020_Electroreduction_of_nitrates_nitrites_and_gaseous_nitrogen_oxides_a_potential_source_of_ammonia_in_dinitr",
  "document_reaction_family": "eNRR",
  "evidence_link_count": 4,
  "paper_admissibility_reasons": [
    "critical_conflict_or_uncertainty"
  ],
  "paper_admissibility_status": "needs_review",
  "paper_id": "P0006_Choi_2020_Electroreduction_of_nitrates_nitrites_and_gaseous_nitrogen_oxides_a_potential_source_of_ammonia_in_dinitr",
  "performance_summary": {
    "primary_result_span_count": 0,
    "quantitative_result_span_count": 0
  },
  "primary_claim_counts": {
    "validation_claim": 1
  },
  "primary_eligible_span_count": 1,
  "review_priority": "high",
  "secondary_context_count": 5,
  "semantic_span_count": 15,
  "validation_gate_summary": {
    "isotope_15N": 1
  }
}
```

- What it supports: a primary-eligible validation span does not by itself make the paper result-supported; unresolved uncertainty keeps the status conservative.
- What it does not support: that isotope validation is complete or that the paper’s scientific conclusions are invalid.
- Review risk: isolated gate counts can be mistaken for a complete validation package.

## 9. ReviewSampleRow

Selection: first row after sorting `semantic_review_sample.csv` by `cleanroom_span_id`. The target and neighbor texts are each a **bounded excerpt**; all human fields remain exactly blank.

```json
{
  "cleanroom_span_id": "CR15_003E8DFC8B8BC6778C2D",
  "document_ref": "input_markdown/P0751_Richard_2024_Power-to-ammonia_synthesis_process_with_membrane_reactors_Techno-_economic_study.md",
  "effective_reaction_family": "unclear",
  "following_paragraph": "The study of catalytic membrane reactors for ammonia synthesis is still a nascent field. In this context, only Zhang et al. (2020) made a significant contr[bounded excerpt truncated]",
  "human_claim_type_correct": "",
  "human_family_correct": "",
  "human_notes": "",
  "human_ownership_correct": "",
  "human_primary_eligibility_correct": "",
  "human_scope_correct": "",
  "linked_evidence_span_ids": [],
  "needs_review": true,
  "paper_admissibility_status": "needs_review",
  "paper_id": "P0751_Richard_2024_Power-to-ammonia_synthesis_process_with_membrane_reactors_Techno-_economic_study",
  "previous_paragraph": "## 1. Introduction",
  "primary_semantic_eligibility": false,
  "review_stratum": "needs_review",
  "run_name": "enrr_cleanroom_v015_20260718",
  "semantic_claim_type": "untyped_claim",
  "target_text": "The PEM technology stands out for its flexibility which makes it very suitable for renewable energy applications but requires higher cost and the use of critic[bounded excerpt truncated]"
}
```

- What it supports: the review export carries a stable audit unit, bounded context, automated fields, and blank human placeholders.
- What it does not support: any completed human review or human-correctness label.
- Review risk: automated columns can anchor a reviewer unless instructions require independent evidence inspection.

## 10. FinalManifest summary

Selection: the single `final_manifest.json`, augmented only with a projection of the corresponding stage statuses and validation result from the same run.

```json
{
  "completed_stages": [
    "ingest",
    "documents",
    "source_nodes",
    "candidates",
    "semantics",
    "links",
    "papers",
    "review",
    "validate"
  ],
  "created_at": "2026-07-18T10:21:58.711528Z",
  "failed_stages": [],
  "pipeline_profile": "document_first_cleanroom_v1",
  "pipeline_status": "completed",
  "run_name": "enrr_cleanroom_v015_20260718",
  "schema_version": "0.15-cleanroom.1",
  "stage_manifest": "manifests/stage_manifest.json",
  "stage_statuses": {
    "candidates": "completed",
    "documents": "completed",
    "ingest": "completed",
    "links": "completed",
    "papers": "completed",
    "review": "completed",
    "semantics": "completed",
    "source_nodes": "completed",
    "validate": "completed"
  },
  "validation_error_count": 0,
  "validation_result": "PASS"
}
```

- What it supports: all nine stages completed and structural/safety validation reported zero errors for this run.
- What it does not support: human semantic accuracy, remote CI status, or scientific comparability.
- Review risk: `completed` can be overread as scientifically validated rather than operationally complete.
