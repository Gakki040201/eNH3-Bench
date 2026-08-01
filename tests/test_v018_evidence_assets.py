from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from scripts.audit_v018_evidence_assets import (
    AuditSources,
    build_inventory,
    build_summary,
    ensure_runtime_outside_repository,
    expected_pilot_manifest,
    select_pilot_corpus,
    validate_pilot_manifest,
    write_runtime_outputs,
)
from scripts.check_v018_evidence_package import (
    canonical_content_sha256,
    validate_evidence_package,
)


SHA_A = "a" * 64


def source_bundle(count: int = 12) -> AuditSources:
    families = [
        "LiNRR",
        "eNRR",
        "NO3RR",
        "NO2RR",
        "unclear",
        "NO3RR",
        "eNRR",
        "unclear",
        "NORR",
        "mixed",
        "eNRR",
        "NO3RR",
        "LiNRR",
    ]
    genres = [
        "primary_research",
        "primary_research",
        "primary_research",
        "primary_research",
        "primary_research",
        "computational_study",
        "review",
        "perspective",
        "primary_research",
        "primary_research",
        "primary_research",
        "primary_research",
        "primary_research",
    ]
    case_types = [
        "primary_evidence_sufficiency",
        "ammonia_quantification_assessment",
        "validation_reliability_assessment",
        "primary_evidence_sufficiency",
        "reactor_process_extraction",
        "claim_ownership_assessment",
        "ammonia_quantification_assessment",
        "paper_scope_classification",
        "validation_reliability_assessment",
        "ammonia_quantification_assessment",
        "reaction_family_identification",
        "ammonia_quantification_assessment",
        "primary_evidence_sufficiency",
    ]
    answerability = [
        "insufficient_evidence",
        "partially_answerable",
        "answerable",
        "insufficient_evidence",
        "partially_answerable",
        "answerable",
        "insufficient_evidence",
        "partially_answerable",
        "partially_answerable",
        "partially_answerable",
        "answerable",
        "answerable",
        "answerable",
    ]
    oa: list[dict[str, object]] = []
    documents: list[dict[str, object]] = []
    spans: list[dict[str, object]] = []
    papers: list[dict[str, object]] = []
    experiments: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    links: list[dict[str, object]] = []
    calibration: list[dict[str, object]] = []
    cases: list[dict[str, object]] = []
    gold: list[dict[str, object]] = []
    review: list[dict[str, object]] = []
    for index in range(count):
        paper_id = f"P{index + 1:04d}"
        long_id = f"{paper_id}_Fixture_{index + 1}"
        oa.append(
            {
                "paper_id": paper_id,
                "validation_status": "valid_pdf",
                "relative_path": f"input_raw/{long_id}.pdf",
                "sha256": SHA_A,
            }
        )
        documents.append(
            {
                "paper_id": long_id,
                "document_ref": f"input_markdown/{long_id}.md",
                "document_reaction_family": families[index],
                "document_genre": genres[index],
                "document_reaction_family_conflict": False,
            }
        )
        spans.append({"paper_id": long_id, "cleanroom_span_id": f"CR15_{index:016X}"})
        gates = {
            "ammonia_quantification": 1 if index in {2, 3, 4} else 0,
            "isotope_15N": 1 if index in {2, 3, 4} else 0,
            "contamination_control": 0,
        }
        papers.append(
            {
                "paper_id": long_id,
                "paper_admissibility_status": "needs_review",
                "validation_gate_summary": gates,
                "reactor_process_summary": {
                    "process_span_count": 0,
                    "reactor_span_count": 1 if index in {4, 11} else 0,
                },
            }
        )
        experiments.append({"paper_id": long_id, "span_id": f"S{index}"})
        claims.append({"paper_id": long_id, "evidence_id": f"E{index}"})
        links.append({"paper_id": long_id, "evidence_link_id": f"L{index}"})
        calibration.append({"paper_id": long_id})
        cases.append(
            {
                "paper_id": long_id,
                "split": "development",
                "case_type": case_types[index],
                "answerability_status": answerability[index],
            }
        )
        gold.append({"paper_id": long_id})
        review.append(
            {
                "paper_id": long_id,
                "human_review_status": "reviewed",
                "human_text_class": "primary_performance",
                "human_maximum_supported_boundary": "cell_metric",
                "human_admissibility_status": "accept_with_controls",
                "human_experiment_decision": "control_required",
            }
        )
    return AuditSources(
        oa_manifest=oa,
        cleanroom_documents=documents,
        cleanroom_spans=spans,
        cleanroom_papers=papers,
        experiment_records=experiments,
        scientific_claims=claims,
        evidence_links=links,
        calibration_records=calibration,
        selective_cases=cases,
        selective_anchors=[],
        gold_records=gold,
        human_review_records=review,
        supplementary_documents=[],
    )


def valid_package() -> dict[str, object]:
    package: dict[str, object] = {
        "schema_version": "0.18-evidence-package.1",
        "package_id": "EP18_0123456789ABCDEF",
        "paper_id": "P0001",
        "source_documents": [
            {
                "source_document_id": "DOC18_0123456789ABCDEF",
                "paper_id": "P0001",
                "document_type": "main",
                "availability_status": "available",
                "source_ref": "documents/P0001.md",
                "sha256": SHA_A,
            }
        ],
        "source_spans": [
            {
                "source_span_id": "CR15_0123456789ABCDEF",
                "paper_id": "P0001",
                "source_document_id": "DOC18_0123456789ABCDEF",
                "start_offset": 0,
                "end_offset": 20,
                "text": "Exact evidence span.",
                "provenance_type": "results",
            }
        ],
        "experiment_records": [
            {
                "experiment_record_id": "EXP18_0123456789ABCDEF",
                "paper_id": "P0001",
                "source_span_ids": ["CR15_0123456789ABCDEF"],
                "measurements": {
                    "faradaic_efficiency": {"status": "reported", "value": 42.0},
                    "stability_hours": {"status": "not_reported"},
                },
            }
        ],
        "scientific_claims": [
            {
                "claim_id": "CLM18_0123456789ABCDEF",
                "paper_id": "P0001",
                "claim_text": "A bounded synthetic claim.",
                "source_span_ids": ["CR15_0123456789ABCDEF"],
                "drafting_status": "machine_drafted",
            }
        ],
        "evidence_links": [
            {
                "evidence_link_id": "EL18_0123456789ABCDEF",
                "paper_id": "P0001",
                "claim_id": "CLM18_0123456789ABCDEF",
                "source_span_id": "CR15_0123456789ABCDEF",
                "support_role": "primary_support",
            }
        ],
        "quality_gates": {
            "passed": True,
            "checks": [
                {"gate_id": gate, "status": "pass"}
                for gate in (
                    "claim_span_binding",
                    "no_hidden_labels",
                    "no_secrets",
                    "relative_paths",
                    "same_paper_binding",
                    "unique_ids",
                )
            ],
            "warnings": [],
        },
        "review_status": {"status": "machine_drafted", "reviewer_ids": []},
        "provenance": {
            "created_by": "deterministic_pipeline",
            "generation_method": "synthetic_test_fixture",
            "source_asset_refs": ["documents/P0001.md"],
            "code_commit": "1" * 40,
        },
        "package_hashes": {
            "algorithm": "sha256",
            "content_sha256": "0" * 64,
            "source_document_hashes": {"DOC18_0123456789ABCDEF": SHA_A},
        },
    }
    package["package_hashes"]["content_sha256"] = canonical_content_sha256(package)  # type: ignore[index]
    return package


def rehash(package: dict[str, object]) -> dict[str, object]:
    package["package_hashes"]["content_sha256"] = canonical_content_sha256(package)  # type: ignore[index]
    return package


class EvidenceAssetAuditTests(unittest.TestCase):
    def test_01_inventory_is_deterministic(self) -> None:
        sources = source_bundle()
        first, first_context = build_inventory(sources)
        reversed_sources = AuditSources(
            **{
                field: list(reversed(getattr(sources, field)))
                for field in sources.__dataclass_fields__
            }
        )
        second, second_context = build_inventory(reversed_sources)
        self.assertEqual(first, second)
        self.assertEqual(first_context, second_context)

    def test_02_duplicate_paper_ids_fail_closed(self) -> None:
        sources = source_bundle()
        duplicate = AuditSources(
            **{
                **{field: getattr(sources, field) for field in sources.__dataclass_fields__},
                "oa_manifest": [*sources.oa_manifest, dict(sources.oa_manifest[0])],
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate paper_id"):
            build_inventory(duplicate)

    def test_03_main_and_si_are_distinct_assets(self) -> None:
        sources = source_bundle()
        supplementary = [{"paper_id": "P0001", "availability_status": "available"}]
        sources = AuditSources(
            **{
                **{field: getattr(sources, field) for field in sources.__dataclass_fields__},
                "supplementary_documents": supplementary,
            }
        )
        inventory, _ = build_inventory(sources)
        self.assertTrue(inventory[0]["main_document_available"])
        self.assertTrue(inventory[0]["supplementary_document_available"])
        self.assertTrue(inventory[1]["main_document_available"])
        self.assertFalse(inventory[1]["supplementary_document_available"])

    def test_04_inventory_uses_manifest_validation_not_filename(self) -> None:
        sources = source_bundle()
        sources.oa_manifest[0]["validation_status"] = "invalid_signature"
        inventory, _ = build_inventory(sources)
        self.assertFalse(inventory[0]["main_document_available"])

    def test_05_selection_is_exactly_12_and_deterministic(self) -> None:
        inventory, context = build_inventory(source_bundle())
        first, first_modes = select_pilot_corpus(
            inventory, excluded_paper_ids=context["excluded_holdout_paper_ids"]
        )
        second, second_modes = select_pilot_corpus(
            reversed(inventory), excluded_paper_ids=context["excluded_holdout_paper_ids"]
        )
        self.assertEqual([row["paper_id"] for row in first], [row["paper_id"] for row in second])
        self.assertEqual(first_modes, second_modes)
        self.assertEqual(len(first), 12)
        self.assertEqual(len({row["paper_id"] for row in first}), 12)

    def test_06_holdout_paper_is_never_selected(self) -> None:
        inventory, _ = build_inventory(source_bundle(13))
        selected, _ = select_pilot_corpus(inventory, excluded_paper_ids={"P0001"})
        self.assertNotIn("P0001", {row["paper_id"] for row in selected})

    def test_07_manifest_contract_allows_only_frozen_fields(self) -> None:
        inventory, context = build_inventory(source_bundle())
        selected, modes = select_pilot_corpus(
            inventory, excluded_paper_ids=context["excluded_holdout_paper_ids"]
        )
        manifest = expected_pilot_manifest(selected, modes)
        validate_pilot_manifest(manifest, manifest)
        manifest["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "only the papers collection"):
            validate_pilot_manifest(manifest, expected_pilot_manifest(selected, modes))

    def test_08_runtime_must_be_outside_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repository = root / "repo"
            repository.mkdir()
            with self.assertRaisesRegex(ValueError, "outside"):
                ensure_runtime_outside_repository(repository / "runtime", repository)
            self.assertEqual(ensure_runtime_outside_repository(root / "runtime", repository), (root / "runtime").resolve())

    def test_09_runtime_writer_creates_only_external_required_outputs(self) -> None:
        inventory, context = build_inventory(source_bundle())
        selected, _ = select_pilot_corpus(inventory)
        summary = build_summary(inventory, context, selected)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repository = root / "repo"
            runtime = root / "runtime"
            repository.mkdir()
            outputs = write_runtime_outputs(runtime, repository, inventory, summary)
            self.assertEqual(
                {path.relative_to(runtime).as_posix() for path in outputs.values()},
                {
                    "audits/v018_asset_inventory.jsonl",
                    "audits/v018_asset_summary.json",
                    "reports/v018_asset_coverage.html",
                    "reports/v018_asset_gaps.csv",
                },
            )
            self.assertFalse(any(repository.iterdir()))

    def test_10_audit_has_no_network_dependency(self) -> None:
        with mock.patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            inventory, context = build_inventory(source_bundle())
            selected, _ = select_pilot_corpus(
                inventory, excluded_paper_ids=context["excluded_holdout_paper_ids"]
            )
        self.assertEqual(len(selected), 12)


class EvidencePackageValidatorTests(unittest.TestCase):
    def test_11_synthetic_valid_package_passes(self) -> None:
        result = validate_evidence_package(valid_package())
        self.assertEqual(result, {
            "schema_version": "0.18-evidence-package.1",
            "package_id": "EP18_0123456789ABCDEF",
            "result": "PASS",
            "error_count": 0,
            "errors": [],
        })

    def test_12_missing_source_documents_fail(self) -> None:
        package = valid_package()
        package["source_documents"] = []
        rehash(package)
        result = validate_evidence_package(package)
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("source_documents" in error for error in result["errors"]))

    def test_13_missing_and_not_reported_remain_distinct(self) -> None:
        package = valid_package()
        package["source_documents"].extend(  # type: ignore[union-attr]
            [
                {
                    "source_document_id": "DOC18_1111111111111111",
                    "paper_id": "P0001",
                    "document_type": "supplementary",
                    "availability_status": "missing",
                    "source_ref": None,
                    "sha256": None,
                },
                {
                    "source_document_id": "DOC18_2222222222222222",
                    "paper_id": "P0001",
                    "document_type": "supplementary",
                    "availability_status": "not_reported",
                    "source_ref": None,
                    "sha256": None,
                },
            ]
        )
        rehash(package)
        self.assertEqual(validate_evidence_package(package)["result"], "PASS")
        measurements = package["experiment_records"][0]["measurements"]  # type: ignore[index]
        measurements["stability_hours"] = {"status": "missing", "value": None}
        rehash(package)
        result = validate_evidence_package(package)
        self.assertTrue(any("must not serialize a value" in error for error in result["errors"]))

    def test_14_source_span_binding_is_enforced(self) -> None:
        package = valid_package()
        package["source_spans"][0]["source_document_id"] = "DOC18_FFFFFFFFFFFFFFFF"  # type: ignore[index]
        rehash(package)
        result = validate_evidence_package(package)
        self.assertTrue(any("source_document_id is unbound" in error for error in result["errors"]))

    def test_15_unbound_claim_is_rejected(self) -> None:
        package = valid_package()
        package["scientific_claims"][0]["source_span_ids"] = ["CR15_UNBOUND00000000"]  # type: ignore[index]
        rehash(package)
        result = validate_evidence_package(package)
        self.assertTrue(any("unbound span" in error for error in result["errors"]))

    def test_16_cross_paper_evidence_is_rejected(self) -> None:
        package = valid_package()
        package["evidence_links"][0]["paper_id"] = "P0002"  # type: ignore[index]
        rehash(package)
        result = validate_evidence_package(package)
        self.assertTrue(any("crosses paper_id boundary" in error for error in result["errors"]))

    def test_17_absolute_path_is_rejected(self) -> None:
        package = valid_package()
        package["source_documents"][0]["source_ref"] = r"C:\private\P0001.md"  # type: ignore[index]
        rehash(package)
        result = validate_evidence_package(package)
        self.assertTrue(any("repository-relative" in error for error in result["errors"]))

    def test_18_secret_field_is_rejected(self) -> None:
        for field, location in (("api_key", "provenance"), ("access_token", "measurements")):
            with self.subTest(field=field):
                package = valid_package()
                if location == "provenance":
                    package["provenance"][field] = "not-a-real-key"  # type: ignore[index]
                else:
                    package["experiment_records"][0]["measurements"][field] = {  # type: ignore[index]
                        "status": "not_reported"
                    }
                rehash(package)
                result = validate_evidence_package(package)
                self.assertTrue(any("forbidden secret" in error for error in result["errors"]))

    def test_19_hidden_label_and_reasoning_fields_are_rejected(self) -> None:
        for field in ("hidden_labels", "reasoning"):
            with self.subTest(field=field):
                package = valid_package()
                package["review_status"][field] = []  # type: ignore[index]
                rehash(package)
                result = validate_evidence_package(package)
                self.assertTrue(any("forbidden secret" in error for error in result["errors"]))

    def test_20_machine_human_and_gold_statuses_are_distinct(self) -> None:
        package = valid_package()
        package["scientific_claims"][0]["drafting_status"] = "gold_accepted"  # type: ignore[index]
        rehash(package)
        result = validate_evidence_package(package)
        self.assertTrue(any("exceeds package review_status" in error for error in result["errors"]))

    def test_21_malformed_packages_fail_closed(self) -> None:
        mutations = (
            lambda package: package.update({"schema_version": "0.18-unknown"}),
            lambda package: package.update({"unexpected": True}),
            lambda package: package["quality_gates"].update({"passed": False}),
            lambda package: package["package_hashes"].update({"content_sha256": "0" * 64}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                package = valid_package()
                mutate(package)
                if package["package_hashes"]["content_sha256"] != "0" * 64:  # type: ignore[index]
                    rehash(package)
                self.assertEqual(validate_evidence_package(package)["result"], "FAIL")


if __name__ == "__main__":
    unittest.main()
