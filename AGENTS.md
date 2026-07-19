# eNH3-Bench repository constraints

These instructions apply to the entire `eNH3-Bench` repository.

1. The repository root is `eNH3-Bench`.
2. Files under the authoritative Gold run are immutable baselines.
3. A Gold change requires a separately updated integrity baseline and explicit user approval before editing Gold.
4. Existing `source_span_id` values must never be renumbered or rewritten.
5. Audit schema `0.13` and its default export behavior must remain backward compatible.
6. New behavior must use an explicit profile or an independent schema version.
7. References, figure or scheme captions, and review tables may provide context, but must never become primary positive support.
8. Evidence links must never cross `paper_id` boundaries.
9. Do not make a real LLM API call unless the user explicitly authorizes it.
10. Every code change must run the full unittest suite and the exact Gold integrity check.
11. Runtime data outputs, PDFs, and full-text Markdown files must not be committed.
12. Never claim a test was run unless it was actually executed.
13. A Stage B span is an exact evidence anchor, not a standalone full-document conclusion.
14. Full document text is stored or referenced once; it must not be copied into every span sample or context packet.
