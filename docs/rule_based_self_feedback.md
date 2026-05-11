# Rule-Based Self-Feedback

eNH3-Bench includes local rule-based draft feedback inspired by the general
idea of self-feedback in scholarly pipelines. It does not use an LLM, does not
revise claims automatically, and does not certify evidence.

The feedback layer highlights risks for minimal human verification:

- Metrics extracted without explicit source grounding.
- Validation controls marked `yes` without explicit source wording.
- Review-like wording that may require `evidence_type = review_summary`.
- Missing NH3 yield units.
- Unclear reaction family or unknown nitrogen source.
- Reliability labels that conflict with validation evidence.

Machine feedback is an audit aid. Human source-grounded verification remains
required before any draft becomes gold.
