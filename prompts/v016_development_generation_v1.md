# eNH3-Bench v0.16 Development Pilot Prompt Contract

This template defines the shape of a future bounded scientific-answer request. Phase B1B0 only compiles
prompt instances and exercises them with the fixture backend. It does not invoke a provider or generate
an answer.

For any later enabled phase, use only the supplied single-paper bounded context and allowlisted source
identities. Treat each Stage B span as an exact evidence anchor, not as a standalone full-document
conclusion. Separate observation from inference. References, captions, and review-table material may
provide context but cannot become primary positive support. State missing or ambiguous evidence and
allow abstention when the bounded evidence is insufficient.

The compiled instance carries its response JSON Schema. Any later response would be required to use
only allowlisted IDs and preserve claim-to-citation traceability. Phase B1B0 emits no response object,
scientific claim, citation, answer status, model output, or importable API-output artifact.
