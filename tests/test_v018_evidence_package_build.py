from __future__ import annotations

import copy
import csv
import hashlib
from html import unescape
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from enh3bench.evidence_package_v018 import (
    FROZEN_PILOT_ORDER,
    QUALITY_GATE_ORDER,
    PaperAssets,
    assemble_evidence_package,
    canonical_output_tree_sha256,
    compare_output_trees,
    explicit_reportable,
    load_frozen_pilot_manifest,
    publish_single_package,
    render_coverage_html,
    stable_id,
    stage_and_publish_packages,
    validate_package_set,
    write_package_set,
)
from scripts.check_v018_evidence_package import (
    canonical_content_sha256,
    validate_evidence_package,
    validate_evidence_package_file,
)


COMMIT = "1" * 40


def manifest_records() -> list[dict[str, object]]:
    return [
        {
            "paper_id": paper_id,
            "selection_reasons": [f"deterministic:{paper_id}"],
            "reaction_family_coverage": ["eNRR"],
            "expected_asset_categories": ["main_document", "cleanroom_source_spans"],
        }
        for paper_id in FROZEN_PILOT_ORDER
    ]


def write_manifest(root: Path) -> Path:
    path = root / "pilot.json"
    path.write_text(json.dumps({"papers": manifest_records()}), encoding="utf-8")
    return path


def span_id(paper_id: str, lane: str) -> str:
    return "CR15_" + hashlib.sha256(f"{paper_id}:{lane}".encode()).hexdigest()[:20].upper()


def synthetic_assets(
    paper_id: str,
    *,
    include_link: bool = True,
    claim_text: str | None = None,
    experiment_text: str | None = None,
    experiment_offsets: tuple[int, int] = (0, 11),
    claim_mapping: dict[str, object] | None = None,
    gold_membership: bool = True,
    review_membership: bool = True,
    reaction_family: str = "eNRR",
) -> PaperAssets:
    claim_text = claim_text if claim_text is not None else f"claim {paper_id}"
    experiment_text = experiment_text if experiment_text is not None else claim_text
    claim_span = span_id(paper_id, "claim")
    evidence_span = span_id(paper_id, "evidence")
    evidence_id = f"E_{paper_id}_001"
    spans = (
        {
            "paper_id": f"{paper_id}_synthetic",
            "cleanroom_span_id": claim_span,
            "source_start_offset": 0,
            "source_end_offset": 11,
            "source_text": f"claim {paper_id}",
            "provenance_type": "primary_body",
        },
        {
            "paper_id": f"{paper_id}_synthetic",
            "cleanroom_span_id": evidence_span,
            "source_start_offset": 20,
            "source_end_offset": 33,
            "source_text": f"support {paper_id}",
            "provenance_type": "primary_body",
        },
    )
    experiment = {
        "paper_id": f"{paper_id}_synthetic",
        "evidence_id": evidence_id,
        "span_id": f"{paper_id}_S001",
        "source_text": experiment_text,
        "source_start_offset": experiment_offsets[0],
        "source_end_offset": experiment_offsets[1],
        "reaction_family": "eNRR",
        "nitrogen_source": "N2",
        "catalyst": None,
        "catalyst_class": "test",
        "electrolyte": None,
        "reactor_type": None,
        "membrane": None,
        "potential_value": 0,
        "potential_unit": "V",
        "potential_reference": None,
        "current_density_mA_cm2": 0,
        "faradaic_efficiency_percent": None,
        "nh3_yield_value": None,
        "nh3_yield_unit": None,
        "nh3_yield_normalized_value": None,
        "nh3_yield_normalized_unit": None,
        "energy_efficiency_percent": None,
        "stability_hours": None,
        "detection_method": "colorimetric",
        "isotope_validation": False,
        "blank_control": "not_reported",
        "contamination_control": "missing",
        "nox_screening": None,
        "reliability_label": "unreviewed",
        "evidence_type": "existing_triage",
    }
    claim = {
        "paper_id": f"{paper_id}_synthetic",
        "evidence_id": evidence_id,
        "source_span": claim_text,
    }
    links = ()
    if include_link:
        links = ({
            "paper_id": f"{paper_id}_synthetic",
            "evidence_link_id": f"CRL15_{paper_id}001",
            "target_cleanroom_span_id": claim_span,
            "evidence_cleanroom_span_id": evidence_span,
            "link_roles": ["quantification_support"],
            "is_context_only": False,
            "source_eligibility": "primary_admissible",
        },)
    mappings = {evidence_id: claim_mapping} if claim_mapping else {}
    sha = hashlib.sha256(f"document {paper_id}".encode()).hexdigest()
    return PaperAssets(
        paper_id=paper_id,
        reaction_family_coverage=(reaction_family,),
        main_document_ref=f"input_markdown/{paper_id}.md",
        main_document_sha256=sha,
        main_document_integrity=True,
        spans=spans,
        experiment_records=(experiment,),
        scientific_claims=(claim,),
        evidence_links=links,
        audit_record={
            "paper_id": paper_id,
            "gold_membership": gold_membership,
            "human_review_membership": review_membership,
            "warnings": [],
        },
        source_asset_refs=("data/accepted/documents.jsonl", "data/accepted/spans.jsonl"),
        claim_status_mappings=mappings,
    )


def builds_for_all() -> dict[str, object]:
    return {
        paper_id: assemble_evidence_package(
            synthetic_assets(paper_id, include_link=paper_id != "P0797"), COMMIT
        )
        for paper_id in FROZEN_PILOT_ORDER
    }


class EvidencePackageIdentityAndAssemblyTests(unittest.TestCase):
    def test_01_frozen_pilot_exact_order(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = write_manifest(Path(name))
            self.assertEqual(
                [row["paper_id"] for row in load_frozen_pilot_manifest(path)],
                list(FROZEN_PILOT_ORDER),
            )

    def test_02_frozen_pilot_rejects_reorder(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            rows = manifest_records()
            rows[0], rows[1] = rows[1], rows[0]
            path = Path(name) / "pilot.json"
            path.write_text(json.dumps({"papers": rows}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_frozen_pilot_manifest(path)

    def test_03_source_document_identity_is_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        second = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        self.assertEqual(first.package["source_documents"], second.package["source_documents"])

    def test_04_package_identity_is_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        second = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        self.assertEqual(first.package["package_id"], second.package["package_id"])

    def test_05_experiment_identity_is_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        second = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        self.assertEqual(first.package["experiment_records"], second.package["experiment_records"])

    def test_06_claim_identity_is_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        second = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        self.assertEqual(first.package["scientific_claims"], second.package["scientific_claims"])

    def test_07_evidence_link_identity_is_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0425"), COMMIT)
        second = assemble_evidence_package(synthetic_assets("P0425"), COMMIT)
        self.assertEqual(first.package["evidence_links"], second.package["evidence_links"])

    def test_08_existing_source_span_id_is_preserved(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        self.assertIn(span_id("P0797", "claim"), {row["source_span_id"] for row in build.package["source_spans"]})

    def test_09_exactly_one_available_main_document(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        available_main = [d for d in package["source_documents"] if d["document_type"] == "main" and d["availability_status"] == "available"]
        self.assertEqual(len(available_main), 1)

    def test_10_si_is_not_inferred_from_filename(self) -> None:
        assets = synthetic_assets("P0797")
        assets = PaperAssets(**{**assets.__dict__, "main_document_ref": "input_markdown/P0797_Supporting_Information.md"})
        package = assemble_evidence_package(assets, COMMIT).package
        si = next(d for d in package["source_documents"] if d["document_type"] == "supplementary")
        self.assertEqual(si["availability_status"], "not_reported")

    def test_11_unavailable_si_has_null_refs(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        si = package["source_documents"][1]
        self.assertIsNone(si["source_ref"])
        self.assertIsNone(si["sha256"])

    def test_12_cross_paper_span_fails(self) -> None:
        assets = synthetic_assets("P0797")
        spans = list(copy.deepcopy(assets.spans))
        spans[0]["paper_id"] = "P0425_other"
        assets = PaperAssets(**{**assets.__dict__, "spans": tuple(spans)})
        with self.assertRaises(ValueError):
            assemble_evidence_package(assets, COMMIT)

    def test_13_cross_paper_experiment_fails(self) -> None:
        assets = synthetic_assets("P0797")
        records = list(copy.deepcopy(assets.experiment_records))
        records[0]["paper_id"] = "P0425_other"
        assets = PaperAssets(**{**assets.__dict__, "experiment_records": tuple(records)})
        with self.assertRaises(ValueError):
            assemble_evidence_package(assets, COMMIT)

    def test_14_cross_paper_claim_fails(self) -> None:
        assets = synthetic_assets("P0797")
        records = list(copy.deepcopy(assets.scientific_claims))
        records[0]["paper_id"] = "P0425_other"
        assets = PaperAssets(**{**assets.__dict__, "scientific_claims": tuple(records)})
        with self.assertRaises(ValueError):
            assemble_evidence_package(assets, COMMIT)

    def test_15_cross_paper_evidence_link_fails(self) -> None:
        assets = synthetic_assets("P0425")
        records = list(copy.deepcopy(assets.evidence_links))
        records[0]["paper_id"] = "P0797_other"
        assets = PaperAssets(**{**assets.__dict__, "evidence_links": tuple(records)})
        with self.assertRaises(ValueError):
            assemble_evidence_package(assets, COMMIT)

    def test_16_unbound_claim_is_excluded_and_queued(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797", claim_text="unbound"), COMMIT)
        self.assertEqual(build.package["scientific_claims"], [])
        self.assertIn("claim_excluded_unbound", {row["reason_code"] for row in build.review_queue})

    def test_17_unbound_experiment_is_excluded_and_queued(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797", experiment_offsets=(1, 11)), COMMIT)
        self.assertEqual(build.package["experiment_records"], [])
        self.assertIn("experiment_record_excluded_unbound", {row["reason_code"] for row in build.review_queue})

    def test_18_p0797_builds_without_links_and_warns(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797", include_link=False), COMMIT)
        self.assertEqual(build.package["evidence_links"], [])
        self.assertIn("existing_evidence_links_unavailable", build.package["quality_gates"]["warnings"])

    def test_19_no_link_is_fabricated_for_p0797(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797", include_link=False), COMMIT).package
        self.assertEqual(len(package["evidence_links"]), 0)

    def test_20_paper_gold_membership_does_not_promote_claim(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797", gold_membership=True), COMMIT).package
        self.assertEqual(package["scientific_claims"][0]["drafting_status"], "machine_drafted")

    def test_21_paper_review_membership_does_not_promote_claim(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797", review_membership=True), COMMIT).package
        self.assertEqual(package["review_status"]["status"], "machine_drafted")

    def test_22_direct_human_mapping_preserves_status(self) -> None:
        mapping = {"status": "human_reviewed", "direct_record_ref": "review/R1", "reviewer_ids": ["REV_001"]}
        package = assemble_evidence_package(synthetic_assets("P0797", claim_mapping=mapping), COMMIT).package
        self.assertEqual(package["scientific_claims"][0]["drafting_status"], "human_reviewed")

    def test_23_direct_gold_mapping_preserves_status(self) -> None:
        mapping = {"status": "gold_accepted", "direct_record_ref": "gold/G1", "reviewer_ids": ["REV_001"]}
        package = assemble_evidence_package(synthetic_assets("P0797", claim_mapping=mapping), COMMIT).package
        self.assertEqual(package["scientific_claims"][0]["drafting_status"], "gold_accepted")

    def test_24_reviewed_status_without_direct_mapping_fails(self) -> None:
        mapping = {"status": "human_reviewed", "reviewer_ids": ["REV_001"]}
        with self.assertRaises(ValueError):
            assemble_evidence_package(synthetic_assets("P0797", claim_mapping=mapping), COMMIT)

    def test_25_machine_package_has_no_reviewer_ids(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        self.assertEqual(package["review_status"], {"status": "machine_drafted", "reviewer_ids": []})


class EvidencePackageValueAndValidationTests(unittest.TestCase):
    def test_26_missing_and_not_reported_remain_distinct(self) -> None:
        self.assertEqual(explicit_reportable({"x": "missing"}, "x"), {"status": "missing"})
        self.assertEqual(explicit_reportable({}, "x"), {"status": "not_reported"})

    def test_27_null_is_not_reported_not_zero(self) -> None:
        self.assertEqual(explicit_reportable({"x": None}, "x"), {"status": "not_reported"})

    def test_28_false_is_preserved(self) -> None:
        self.assertEqual(explicit_reportable({"x": False}, "x"), {"status": "reported", "value": False})

    def test_29_zero_is_preserved(self) -> None:
        self.assertEqual(explicit_reportable({"x": 0}, "x"), {"status": "reported", "value": 0})

    def test_30_empty_string_is_missing(self) -> None:
        self.assertEqual(explicit_reportable({"x": ""}, "x"), {"status": "missing"})

    def test_31_package_source_refs_are_relative(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        refs = [d["source_ref"] for d in package["source_documents"] if d["source_ref"]]
        refs.extend(package["provenance"]["source_asset_refs"])
        self.assertTrue(all(":" not in ref and "\\" not in ref and not ref.startswith("/") for ref in refs))

    def test_32_absolute_source_ref_fails_closed(self) -> None:
        assets = synthetic_assets("P0797")
        assets = PaperAssets(**{**assets.__dict__, "main_document_ref": "C:/secret/P0797.md"})
        with self.assertRaises(ValueError):
            assemble_evidence_package(assets, COMMIT)

    def test_33_package_contains_no_credential_fields(self) -> None:
        text = json.dumps(assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package).lower()
        self.assertNotIn('"api_key"', text)
        self.assertNotIn('"credential"', text)

    def test_34_package_contains_no_hidden_labels(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        self.assertFalse(any("hidden_label" in key for key in _all_keys(package)))

    def test_35_package_contains_no_model_reasoning(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        self.assertFalse(any(key in {"reasoning", "model_reasoning", "chain_of_thought"} for key in _all_keys(package)))

    def test_36_package_hash_recomputes_exactly(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        self.assertEqual(package["package_hashes"]["content_sha256"], canonical_content_sha256(package))

    def test_37_source_document_hash_map_is_exact(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        available = {d["source_document_id"]: d["sha256"] for d in package["source_documents"] if d["availability_status"] == "available"}
        self.assertEqual(package["package_hashes"]["source_document_hashes"], available)

    def test_38_independent_validator_passes_synthetic_package(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        self.assertEqual(validate_evidence_package(package)["result"], "PASS")

    def test_39_independent_validator_rejects_tamper(self) -> None:
        package = copy.deepcopy(assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package)
        package["scientific_claims"][0]["paper_id"] = "P0425"
        self.assertEqual(validate_evidence_package(package)["result"], "FAIL")

    def test_40_all_a1_quality_gates_are_present_and_pass(self) -> None:
        package = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).package
        self.assertEqual([row["gate_id"] for row in package["quality_gates"]["checks"]], list(QUALITY_GATE_ORDER))
        self.assertTrue(all(row["status"] == "pass" for row in package["quality_gates"]["checks"]))


class EvidencePackageOutputSetTests(unittest.TestCase):
    def test_41_all_paper_build_creates_exactly_12_directories(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            write_package_set(root, manifest_records(), builds_for_all())
            self.assertEqual(sorted(p.name for p in (root / "packages").iterdir()), sorted(FROZEN_PILOT_ORDER))

    def test_42_single_paper_publish_accepts_frozen_id(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            build = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
            publish_single_package(name, "P0797", build, clean=False)
            self.assertTrue((Path(name) / "packages" / "P0797" / "evidence_package.json").is_file())

    def test_43_nonpilot_assembly_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            assemble_evidence_package(synthetic_assets("P9999"), COMMIT)

    def test_44_read_back_package_validates(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            build = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
            publish_single_package(name, "P0797", build, clean=False)
            result = validate_evidence_package_file(Path(name) / "packages" / "P0797" / "evidence_package.json")
            self.assertEqual(result["result"], "PASS")

    def test_45_atomic_staging_refuses_unrequested_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = write_manifest(root)
            builds = builds_for_all()
            stage_and_publish_packages(root, manifest_records(), builds, clean=False, pilot_manifest_path=manifest)
            with self.assertRaises(FileExistsError):
                stage_and_publish_packages(root, manifest_records(), builds, clean=False, pilot_manifest_path=manifest)

    def test_46_failed_stage_leaves_previous_valid_package_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = write_manifest(root)
            builds = builds_for_all()
            stage_and_publish_packages(root, manifest_records(), builds, clean=False, pilot_manifest_path=manifest)
            package_path = root / "packages" / "P0797" / "evidence_package.json"
            before = package_path.read_bytes()
            bad = dict(builds)
            broken = copy.deepcopy(bad["P0797"])
            broken.package["package_hashes"]["content_sha256"] = "0" * 64
            bad["P0797"] = broken
            with self.assertRaises(ValueError):
                stage_and_publish_packages(root, manifest_records(), bad, clean=True, pilot_manifest_path=manifest)
            self.assertEqual(package_path.read_bytes(), before)

    def test_47_set_validator_requires_exactly_12_packages(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = write_manifest(root)
            write_package_set(root, manifest_records(), builds_for_all())
            self.assertEqual(validate_package_set(root, manifest)["stage"], "COMPLETE")

    def test_48_set_validator_rejects_extra_directory(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = write_manifest(root)
            write_package_set(root, manifest_records(), builds_for_all())
            (root / "packages" / "P9999").mkdir()
            result = validate_package_set(root, manifest)
            self.assertEqual(result["stage"], "INVALID")

    def test_49_set_validator_marks_missing_package_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = write_manifest(root)
            write_package_set(root, manifest_records(), builds_for_all())
            target = root / "packages" / "P0312"
            for path in target.iterdir():
                path.unlink()
            target.rmdir()
            result = validate_package_set(root, manifest)
            self.assertEqual(result["stage"], "INCOMPLETE")

    def test_50_package_index_preserves_frozen_order(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            write_package_set(root, manifest_records(), builds_for_all())
            index = json.loads((root / "reports" / "v018_a1_package_index.json").read_text())
            self.assertEqual([row["paper_id"] for row in index["packages"]], list(FROZEN_PILOT_ORDER))

    def test_51_index_hashes_match_packages(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            write_package_set(root, manifest_records(), builds_for_all())
            index = json.loads((root / "reports" / "v018_a1_package_index.json").read_text())
            for row in index["packages"]:
                package = json.loads((root / row["package_path"]).read_text())
                self.assertEqual(row["content_sha256"], canonical_content_sha256(package))

    def test_52_review_queue_ids_and_order_are_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0797", include_link=False), COMMIT)
        second = assemble_evidence_package(synthetic_assets("P0797", include_link=False), COMMIT)
        self.assertEqual(first.review_queue, second.review_queue)

    def test_53_coverage_json_is_deterministic(self) -> None:
        first = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).coverage
        second = assemble_evidence_package(synthetic_assets("P0797"), COMMIT).coverage
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_54_html_escapes_source_controlled_values(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797", reaction_family="<script>alert(1)</script>"), COMMIT)
        html = render_coverage_html(build.coverage)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_55_html_has_no_external_network_dependency(self) -> None:
        html = render_coverage_html(assemble_evidence_package(synthetic_assets("P0797"), COMMIT).coverage).lower()
        self.assertNotIn("<script", html)
        self.assertNotIn("src=", html)
        self.assertNotIn("href=", html)
        self.assertNotIn("@import", html)

    def test_56_two_output_roots_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            builds = builds_for_all()
            write_package_set(first, manifest_records(), builds)
            write_package_set(second, manifest_records(), builds)
            result = compare_output_trees(first, second)
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(result["first_tree_sha256"], result["second_tree_sha256"])

    def test_57_build_does_not_access_network(self) -> None:
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            assemble_evidence_package(synthetic_assets("P0797"), COMMIT)

    def test_58_library_has_no_f_drive_dependency(self) -> None:
        source = (Path(__file__).parents[1] / "enh3bench" / "evidence_package_v018.py").read_text(encoding="utf-8")
        self.assertNotIn("F:\\", source)

    def test_59_library_does_not_read_environment_credentials(self) -> None:
        source = (Path(__file__).parents[1] / "enh3bench" / "evidence_package_v018.py").read_text(encoding="utf-8")
        self.assertNotIn("os.environ", source)
        self.assertNotIn("getenv(", source)

    def test_60_no_nonpilot_or_holdout_paper_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = write_manifest(Path(name))
            ids = {row["paper_id"] for row in load_frozen_pilot_manifest(path)}
            self.assertEqual(ids, set(FROZEN_PILOT_ORDER))

    def test_61_summary_counts_actual_files(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            summary = write_package_set(root, manifest_records(), builds_for_all())
            self.assertEqual(summary["pilot_count"], len(list((root / "packages").iterdir())))
            self.assertEqual(summary["valid_package_count"], 12)

    def test_62_tree_hash_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            write_package_set(root, manifest_records(), builds_for_all())
            self.assertEqual(canonical_output_tree_sha256(root), canonical_output_tree_sha256(root))

    def test_63_p0797_review_queue_contains_no_link_gap(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797", include_link=False), COMMIT)
        reasons = [row["reason_code"] for row in build.review_queue]
        self.assertIn("existing_evidence_links_unavailable", reasons)

    def test_64_paper_membership_is_coverage_not_claim_acceptance(self) -> None:
        build = assemble_evidence_package(synthetic_assets("P0797"), COMMIT)
        self.assertTrue(build.coverage["gold_membership"])
        self.assertTrue(build.coverage["human_review_membership"])
        self.assertEqual(build.package["review_status"]["status"], "machine_drafted")

    def test_65_claim_text_is_preserved_exactly(self) -> None:
        text = "claim P0797"
        build = assemble_evidence_package(synthetic_assets("P0797", claim_text=text), COMMIT)
        self.assertEqual(build.package["scientific_claims"][0]["claim_text"], text)


def _all_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_all_keys(child))
    return keys


if __name__ == "__main__":
    unittest.main()
