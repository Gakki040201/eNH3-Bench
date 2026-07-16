# Stage B Semantic Sentinel Sample

Deterministic safety sentinels for document reaction family, result-bearing performance,
validation-gate regex safety, document genre, and cited-claim ownership.

- Cases: 12
- Passed: 12
- Overall pass: `True`

## 1. P0090 nitrate family correction

- case_id: `SB_SENTINEL_01`
- input: `{"paper_id": "P0090"}`
- expected: `{"document_families": ["NO3RR"], "primary_effective_eNRR_span_ids": []}`
- actual: `{"document_families": ["NO3RR"], "packet_count": 15, "primary_effective_eNRR_span_ids": [], "primary_eligible_count": 4}`
- pass: `True`

## 2. FeS is not FE performance

- case_id: `SB_SENTINEL_02`
- input: `"FeS catalyst was synthesized."`
- expected: `{"semantic_claim_type_not": "performance_result_claim"}`
- actual: `{"semantic_claim_type": "performance_context_claim"}`
- pass: `True`

## 3. Qualitative high yield is context

- case_id: `SB_SENTINEL_03`
- input: `"The catalyst showed high ammonia yield."`
- expected: `{"semantic_claim_type": "performance_context_claim"}`
- actual: `{"semantic_claim_type": "performance_context_claim"}`
- pass: `True`

## 4. Explicit 15N is positive

- case_id: `SB_SENTINEL_04`
- input: `"15N2 validation"`
- expected: `{"satisfied": true}`
- actual: `{"gate_conflict": false, "gate_detection_signals": ["target_text_isotope_15N"], "gate_detection_source": "target_text", "satisfied": true}`
- pass: `True`

## 5. Generic isotope is not 15N

- case_id: `SB_SENTINEL_05`
- input: `"isotope-labelled material"`
- expected: `{"satisfied": false}`
- actual: `{"gate_conflict": false, "gate_detection_signals": [], "gate_detection_source": "", "satisfied": false}`
- pass: `True`

## 6. English no gas is not NO feed

- case_id: `SB_SENTINEL_06`
- input: `"no gas was supplied"`
- expected: `{"satisfied": false}`
- actual: `{"gate_conflict": false, "gate_detection_signals": ["target_text_NO_source_defined_negated"], "gate_detection_source": "", "satisfied": false}`
- pass: `True`

## 7. Uppercase NO concentration is a source

- case_id: `SB_SENTINEL_07`
- input: `"10% NO in Ar"`
- expected: `{"satisfied": true}`
- actual: `{"gate_conflict": false, "gate_detection_signals": ["target_text_NO_source_defined"], "gate_detection_source": "target_text", "satisfied": true}`
- pass: `True`

## 8. Negated mass balance is not coverage

- case_id: `SB_SENTINEL_08`
- input: `"no mass balance was reported"`
- expected: `{"satisfied": false}`
- actual: `{"gate_conflict": false, "gate_detection_signals": ["target_text_NOx_balance_negated"], "gate_detection_source": "", "satisfied": false}`
- pass: `True`

## 9. NADH NH4 assay is quantification

- case_id: `SB_SENTINEL_09`
- input: `"NH4+ concentration was measured by an NADH consumption assay."`
- expected: `{"ammonia_quantification": true}`
- actual: `{"ammonia_quantification": true}`
- pass: `True`

## 10. Gas purification trap is not quantification

- case_id: `SB_SENTINEL_10`
- input: `"The N2 feed passed through an acid trap to remove adventitious NH3."`
- expected: `{"ammonia_quantification": false, "trap": true}`
- actual: `{"ammonia_quantification": false, "trap": true}`
- pass: `True`

## 11. Review title overrides generic Article type

- case_id: `SB_SENTINEL_11`
- input: `{"article_type": "Article", "title": "A critical review..."}`
- expected: `{"document_genre": "review"}`
- actual: `{"document_genre": "review"}`
- pass: `True`

## 12. Bracketed cited-author action is external

- case_id: `SB_SENTINEL_12`
- input: `"Yang et al. [12] synthesized the catalyst."`
- expected: `{"claim_ownership": "external_or_cited_authors", "span_claim_scope": "external_or_cited_work"}`
- actual: `{"claim_ownership": "external_or_cited_authors", "span_claim_scope": "external_or_cited_work"}`
- pass: `True`
