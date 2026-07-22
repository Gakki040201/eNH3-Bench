# eNH3-Bench v0.16 Development Pilot Prompt Contract

Phase B1B0 compiles this contract and exercises it only with the offline fixture backend. It does not
invoke a provider or generate a scientific answer. Any future enabled generation phase must follow all
rules below.

1. Use only the supplied single-paper bounded context and the supplied allowlisted source identities.
2. Do not supplement the answer from memory, training data, external papers, or outside knowledge.
3. Do not guess missing experimental conditions.
4. Do not fabricate a DOI, numerical value, material, method, citation, or reaction condition.
5. Bind every substantive claim to allowlisted source span IDs or evidence link IDs.
6. Classify claim ownership as `author_result`, `external_reference`, or `uncertain_ownership` when
   applicable; use `method_or_context` and `negative_evidence` for those distinct claim roles.
7. References, figure or scheme captions, review tables, and cited literature do not automatically
   constitute primary evidence for a result owned by the paper's authors.
8. When ammonia or other requested quantification is missing, explicitly state that the bounded
   evidence does not provide the requested quantification.
9. When validation evidence is missing, explicitly state which validation support is absent.
10. Insufficient evidence does not automatically require abstention.
11. When the bounded evidence supports a negative conclusion, answer that negative conclusion normally
    and bind it to its evidence rather than abstaining solely because positive evidence is absent.
12. Set `answer_status` to exactly one of `answered`, `partially_answered`, or `abstained`.
13. Output only one JSON object that conforms to the supplied response JSON Schema.
14. Do not wrap the JSON object in a Markdown code fence and do not emit prose outside the object.
15. Do not output fields that are not defined by the response schema.
16. Do not use a source span ID or evidence link ID outside the supplied allowlists.
17. Mark every unsupported or uncertain claim explicitly with the corresponding `support_status`.
18. Preserve claim-to-citation traceability: each substantive claim must be linked through claim IDs and
    citations to its allowlisted source span IDs or evidence link IDs.

Treat every Stage B span as an exact evidence anchor, not as a standalone full-document conclusion.
Separate direct observation from inference and describe material ambiguity. The compiled instance is
self-contained: it includes this exact contract text, the bounded source context, the source allowlists,
and the strict response JSON Schema. Phase B1B0 itself emits no response object, scientific claim,
citation, answer status, model output, or importable API-output artifact.
