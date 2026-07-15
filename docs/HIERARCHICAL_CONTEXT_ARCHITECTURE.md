# Hierarchical Docling Context Architecture

Stage B treats the complete Docling Markdown document as context and each source span as an exact evidence anchor. It does not infer a paper-level aggregate claim.

```text
PDF
  -> Docling Markdown                       enh3bench/markdown_converter.py
  -> document_loader                       enh3bench/document_loader.py
  -> section blocks / paragraph offsets    enh3bench/section_context.py
  -> candidate span with source offsets    enh3bench/span_finder.py
  -> evidence bundle raw_record             enh3bench/evidence_bundle.py
  -> hierarchical context                  enh3bench/context_packet.py
  -> unique evidence items
  -> later paper-level aggregation (not implemented in Stage B)
```

## Ownership and storage

`enh3bench/markdown_converter.py` produces repository-local Markdown. `enh3bench/document_loader.py` isolates conversion front matter and loads each Markdown body once. `enh3bench/section_context.py` provides the canonical section hierarchy; the hierarchical index adds paragraph offsets without replacing that section parser. `enh3bench/span_finder.py` emits candidate anchors and source offsets, which are preserved through `enh3bench/evidence_bundle.py` and promoted by `enh3bench/context_packet.py`.

The in-memory document index owns full body text. A packet contains a repository-relative `document_ref`, body SHA-256, target mapping, bounded local paragraphs, and a bounded section chunk. It never serializes the complete document body.

## Evidence semantics

Evidence linking is restricted to the same paper and uses normalized thresholded scores. One span is serialized once in `evidence_items`; multiple evidence roles are represented by `link_roles` and `evidence_role_index`. References, captions, review tables, and generic background may appear only as context hints and cannot support a positive claim boundary.

Claim-support sufficiency is separate from classification sufficiency. Required controls are selected from `enh3bench.reaction_profiles`, so nitrate or nitrite reactants are not confused with eNRR impurity controls.
