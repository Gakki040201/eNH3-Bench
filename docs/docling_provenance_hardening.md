# Docling Provenance Hardening

Phase B adds provenance hardening before BoundaryLedger evidence bundles and claim-rights adjudication.

## Why provenance is needed

Electrochemical ammonia papers reuse the same terms across very different document regions. FE, yield, 15N, NOx, electrolyte, and catalyst names may appear in primary body text, literature-review tables, figure captions, reference lists, front matter, metadata, or supplementary material. BoundaryLedger should not treat those locations as equally admissible.

Only primary experimental body-like text can support primary performance claim rights directly. Tables, captions, references, metadata, and front matter must be marked before the claim-rights engine decides the maximum supported boundary.

## Why Markdown alone is insufficient

Markdown conversion preserves text but often loses document structure. A converted span may contain a table, caption, reference list, YAML-like conversion metadata, or primary results prose. Without provenance hardening, a classifier can see performance terms and mislabel context or reference material as primary performance evidence.

The Phase B layer restores a lightweight document-structure signal using Docling JSON when available and deterministic heuristics when it is not.

## Tables, captions, references, and primary body evidence

- Primary body text includes body, abstract, methods, results, and discussion provenance.
- Review tables remain secondary summaries and cannot become primary performance evidence.
- Ordinary tables may support cell-metric extraction only when they look like the paper's own result table, and still require paired body text for stronger claims.
- Figure and scheme captions are context-only unless paired with primary body evidence.
- References, bibliography, front matter, metadata, and copyright notes are low trust for primary performance boundaries.
- Supplementary spans can support extraction but require cross-checking against primary source linkage.

## How provenance constrains claim rights

Provenance dominates text class when the two disagree. For example, a span labelled primary_performance but inferred as reference provenance is rejected as low-trust provenance and receives a text_class_provenance_conflict risk flag.

The claim-rights ledger records:

- provenance_type
- provenance_confidence
- provenance_signals
- is_primary_admissible
- is_secondary_or_context
- is_reject_or_low_trust
- provenance_constrained
- text_class_provenance_conflict

These fields make it clear when a BoundaryLedger decision came from source-location constraints rather than metric content alone.

## Docling absorption without copying source

This repository does not copy Docling code or require Docling JSON for old runs. If Docling JSON is present, `scripts/export_docling_provenance.py` reads common JSON layouts and preserves labels, text, page, block type, section, provenance, and raw records where available. If no JSON is present, it falls back to classified spans and heuristic provenance inference.

Docling's document-structure concept is absorbed as a provenance principle, not as vendored external implementation.
