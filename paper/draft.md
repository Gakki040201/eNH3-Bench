# eNH3-Bench: A Reliability-Aware Benchmark for AI-Assisted Extraction of Electrochemical Ammonia Synthesis Evidence

## Abstract

Electrochemical ammonia synthesis literature spans N2 reduction, lithium-mediated N2 reduction, nitrate reduction, nitrite reduction, nitric oxide reduction, and mixed nitrogen-source systems. eNH3-Bench is a reproducible benchmark for extracting source-grounded evidence from this literature and evaluating whether extracted claims are reliably validated. The benchmark emphasizes structured evidence, unit normalization, validation-status accuracy, source grounding, and hallucination measurement. This draft outlines the dataset construction plan, annotation schema, baseline methods, evaluation metrics, and reporting workflow for a no-API benchmark core.

## Introduction

AI-assisted literature extraction can accelerate evidence synthesis, but electrochemical ammonia synthesis claims are unusually sensitive to validation context. Reported ammonia can arise from N2, nitrate, nitrite, nitric oxide, NOx contamination, catalyst impurities, or background ammonia. A benchmark for this domain therefore needs to assess not only extraction accuracy but also whether systems correctly identify controls, isotope validation, contamination screening, and unsupported claims.

## Dataset Construction

The dataset is organized around paper records, source spans, gold evidence records, predictions, and reports. Initial examples are synthetic placeholders used to define file formats and local tests. Future benchmark versions will add curated spans from primary research, protocols, reassessments, reviews, and mixed-system studies without requiring API access in the core evaluation pipeline.

## Schema and Annotation Protocol

The gold schema includes paper metadata and evidence-level fields covering reaction family, nitrogen source, catalyst, electrolyte, reactor context, reported metrics, validation controls, reliability labels, and curator notes. Annotators select compact source spans and fill only fields grounded in the span or immediate paper context. Reliability labels from A to Reject reflect validation strength rather than novelty or performance quality.

## Baselines

The initial baseline is a no-API rule-based extractor. It uses lightweight lexical heuristics to classify reaction families, detect nitrogen sources, identify validation controls, and extract selected numeric metrics such as Faradaic efficiency, ammonia yield, potential, current density, and stability duration. This baseline is intentionally simple so that later AI-assisted systems can be compared against a reproducible local reference point.

## Evaluation Metrics

Categorical fields are evaluated by normalized exact match. Numeric fields are evaluated with absolute or relative tolerances. The benchmark also reports hallucination rate for unsupported filled fields and missing field rate for gold-supported fields omitted by predictions. These metrics are designed to separate general extraction skill from reliability-aware evidence grounding.

## Results

The current repository exports Markdown result tables from local evaluation JSON. The initial synthetic example run demonstrates the reporting format rather than final benchmark performance. Full benchmark results will compare the rule baseline with future no-API and API-optional systems under controlled settings.

## Error Analysis

The error taxonomy separates categorical disagreement, numeric extraction error, unsupported filled fields, omitted supported fields, and missing prediction entries. Particular attention is given to reliability-label errors because validation assessment is central to the benchmark contribution.

## Discussion

eNH3-Bench is designed as a benchmark, not a software product. Its contribution is a reliability-aware evidence schema and evaluation protocol for electrochemical ammonia synthesis literature across multiple nitrogen-source systems. The benchmark can help characterize where extraction systems succeed, where they overfill unsupported details, and where they fail to identify validation requirements.

## Limitations

The current phase uses synthetic example data and a rule-based baseline. It does not parse real PDFs, scrape websites, train models, or call external APIs. The schema and metrics may need revision after pilot annotation on real literature spans, especially for ambiguous mixed-source systems and reassessment articles.

## Conclusion

eNH3-Bench provides a local, reproducible foundation for evaluating AI-assisted extraction and reliability validation in electrochemical ammonia synthesis literature. The benchmark prioritizes source grounding, validation controls, and transparent error analysis over model-specific tooling.
