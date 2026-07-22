from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import math
import os
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock
import uuid

from enh3bench.calibration_package import tree_hash
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import read_json, read_jsonl, write_json, write_jsonl
from enh3bench.e2e_eval_validation import validate_selective_eval_package
from enh3bench.generation_pilot import (
    ANSWERABILITY_STATUSES,
    CASE_TYPES,
    COMPILED_PROMPT_FIELDS,
    COST_ESTIMATE_SCHEMA_VERSION,
    DEFAULT_PROMPT_TEMPLATE,
    EVALUATOR_ONLY_FIELDS,
    EXECUTION_ONLY_FIELDS,
    FixtureGenerationBackend,
    GENERATION_BACKEND_INTERFACE_VERSION,
    GENERATION_PILOT_PROFILE,
    GENERATION_PROMPT_VERSION,
    GENERATION_RUN_SCHEMA_VERSION,
    GENERATOR_BATCH_FIELDS,
    GenerationBackend,
    PILOT_CASE_COUNT,
    RECEIPT_FIELDS,
    REQUEST_ENVELOPE_FIELDS,
    RESPONSE_JSON_SCHEMA,
    build_development_pilot,
    estimate_generation_cost,
    get_generation_backend,
    normalized_artifact_hash,
    prepare_generation_prompts,
    reproducibility_hashes,
    resolve_external_run_target,
    run_generation_dry_run,
    select_pilot_cases,
    validate_generation_pilot,
)
from scripts import build_development_pilot as build_cli
from scripts import check_generation_pilot as check_cli
from scripts import estimate_generation_cost as estimate_cli
from scripts import prepare_generation_prompts as prepare_cli
from scripts import run_generation_dry_run as dry_run_cli
from tests.selective_eval_test_helpers import create_source_calibration_fixture


ROOT = Path(__file__).resolve().parents[1]


class ExplodingFixtureBackend:
    backend_name = "fixture"
    backend_version = "fixture-generation-v1"

    def __init__(self, explode_at: int = 4) -> None:
        self.delegate = FixtureGenerationBackend()
        self.calls = 0
        self.explode_at = explode_at

    def prepare_request(self, prompt_instance: dict, *, generation_run_name: str, created_at_utc: str) -> dict:
        return self.delegate.prepare_request(
            prompt_instance, generation_run_name=generation_run_name, created_at_utc=created_at_utc,
        )

    def execute(self, request_envelope: dict, *, created_at_utc: str) -> dict:
        self.calls += 1
        if self.calls == self.explode_at:
            raise ValueError("fixture_execution_injected_failure")
        return self.delegate.execute(request_envelope, created_at_utc=created_at_utc)

    def parse_response(self, value: dict) -> dict:
        return self.delegate.parse_response(value)


class GenerationPilotV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.calibration_root = cls.base / "source/calibration"
        create_source_calibration_fixture(cls.calibration_root, "calibration_fixture")
        cls.eval_root = cls.base / "source/selective_eval"
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture",
            source_calibration_root=cls.calibration_root,
            selective_eval_run_name="eval",
            selective_eval_root=cls.eval_root,
            clean=True,
            validate_source_package=False,
        )
        cls.output_root = cls.base / "external/v016_b1b0"
        cls.baseline_name = "baseline"
        cls._build(cls.baseline_name)
        prepare_generation_prompts(
            generation_run_name=cls.baseline_name, generation_root=cls.output_root,
        )
        run_generation_dry_run(
            generation_run_name=cls.baseline_name, generation_root=cls.output_root,
        )
        estimate_generation_cost(
            generation_run_name=cls.baseline_name, generation_root=cls.output_root,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    @classmethod
    def _build(cls, name: str, *, clean: bool = False) -> Path:
        build_development_pilot(
            selective_eval_run_name="eval",
            selective_eval_root=cls.eval_root,
            source_calibration_root=cls.calibration_root,
            generation_run_name=name,
            generation_root=cls.output_root,
            clean=clean,
            validate_source_package=False,
        )
        return cls.output_root / name

    @classmethod
    def _full(cls, name: str) -> Path:
        run = cls._build(name)
        prepare_generation_prompts(generation_run_name=name, generation_root=cls.output_root)
        run_generation_dry_run(generation_run_name=name, generation_root=cls.output_root)
        estimate_generation_cost(generation_run_name=name, generation_root=cls.output_root)
        return run

    def _unique(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _baseline(self) -> Path:
        return self.output_root / self.baseline_name

    def _copy_baseline(self, prefix: str) -> tuple[str, Path]:
        name = self._unique(prefix)
        target = self.output_root / name
        shutil.copytree(self._baseline(), target)
        manifest_path = target / "manifests/generation_run_manifest.json"
        manifest = read_json(manifest_path)
        manifest["generation_run_name"] = name
        write_json(manifest_path, manifest)
        envelope_path = target / "execution/request_envelopes.jsonl"
        envelopes = read_jsonl(envelope_path)
        for row in envelopes:
            row["generation_run_name"] = name
        write_jsonl(envelope_path, envelopes)
        return name, target

    def _cases(self) -> list[dict]:
        return read_jsonl(self.eval_root / "eval/cases/e2e_case_frame.jsonl")

    def _validate(self, name: str) -> dict:
        return validate_generation_pilot(
            generation_run_name=name,
            generation_root=self.output_root,
            selective_eval_root=self.eval_root,
            source_calibration_root=self.calibration_root,
            check_source_package=False,
        )

    def test_01_version_constants_are_exact(self) -> None:
        self.assertEqual(GENERATION_RUN_SCHEMA_VERSION, "0.16-generation-run.1")
        self.assertEqual(GENERATION_PROMPT_VERSION, "v016-development-generation-v1")
        self.assertEqual(GENERATION_PILOT_PROFILE, "development_seven_case_pilot_v1")
        self.assertEqual(GENERATION_BACKEND_INTERFACE_VERSION, "generation-backend-v1")
        self.assertEqual(COST_ESTIMATE_SCHEMA_VERSION, "0.16-generation-cost.1")

    def test_02_selection_has_seven_cases(self) -> None:
        self.assertEqual(len(select_pilot_cases(self._cases())), PILOT_CASE_COUNT)

    def test_03_selection_has_seven_types(self) -> None:
        rows = select_pilot_cases(self._cases())
        self.assertEqual({row["case_type"] for row in rows}, set(CASE_TYPES))

    def test_04_selection_has_seven_unique_papers(self) -> None:
        rows = select_pilot_cases(self._cases())
        self.assertEqual(len({row["paper_id"] for row in rows}), PILOT_CASE_COUNT)

    def test_05_selection_is_development_only(self) -> None:
        case_by_id = {row["case_id"]: row for row in self._cases()}
        rows = select_pilot_cases(self._cases())
        self.assertTrue(all(case_by_id[row["case_id"]]["split"] == "development" for row in rows))

    def test_06_selection_meets_answerability_minimums(self) -> None:
        rows = select_pilot_cases(self._cases())
        for status in ANSWERABILITY_STATUSES:
            self.assertGreaterEqual(sum(row["answerability_status"] == status for row in rows), 2)

    def test_07_selection_is_deterministic(self) -> None:
        self.assertEqual(select_pilot_cases(self._cases()), select_pilot_cases(list(reversed(self._cases()))))

    def test_08_selection_stable_ranks_are_sha256(self) -> None:
        for row in select_pilot_cases(self._cases()):
            self.assertRegex(row["stable_rank_sha256"], r"^[0-9a-f]{64}$")

    def test_09_selection_reasons_bind_diversity_and_rank(self) -> None:
        for row in select_pilot_cases(self._cases()):
            text = "|".join(row["selection_reasons"])
            self.assertIn("answerability_minimum_two_per_status", text)
            self.assertIn("stable_combination_rank=", text)

    def test_10_selection_manifest_retains_evaluator_metadata(self) -> None:
        manifest = read_json(self._baseline() / "pilot/pilot_selection_manifest.json")
        row = manifest["selected_cases"][0]
        self.assertIn("answerability_status", row)
        self.assertIn("automatic_case_risk_tier", row)
        self.assertIn("automatic_signal_stratum", row)

    def test_11_generator_batch_field_set_is_exact(self) -> None:
        self.assertEqual(GENERATOR_BATCH_FIELDS, {
            "schema_version", "profile", "case_id", "paper_id", "question",
            "expected_answer_contract", "required_answer_sections",
            "allowed_source_span_ids", "allowed_evidence_link_ids",
            "bounded_source_context", "abstention_allowed", "source_manifest_sha256",
        })
        rows = read_jsonl(self._baseline() / "pilot/development_pilot_batch.jsonl")
        self.assertTrue(all(set(row) == GENERATOR_BATCH_FIELDS for row in rows))

    def test_12_generator_batch_has_metadata_firewall(self) -> None:
        rows = read_jsonl(self._baseline() / "pilot/development_pilot_batch.jsonl")
        self.assertTrue(all(not (set(row) & EVALUATOR_ONLY_FIELDS) for row in rows))

    def test_13_external_root_rejects_repository_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "must_be_external"):
            resolve_external_run_target(ROOT / "runtime", "pilot")

    def test_14_build_writes_only_blank_pilot_contract(self) -> None:
        run = self._build(self._unique("build_only"))
        files = {path.relative_to(run).as_posix() for path in run.rglob("*") if path.is_file()}
        self.assertEqual(files, {
            "manifests/generation_run_manifest.json",
            "pilot/pilot_selection_manifest.json",
            "pilot/development_pilot_batch.jsonl",
        })

    def test_15_build_never_creates_api_output_artifact(self) -> None:
        self.assertFalse((self._baseline() / "outputs/api_outputs.jsonl").exists())

    def test_16_build_source_tree_is_unchanged(self) -> None:
        manifest = read_json(self._baseline() / "manifests/generation_run_manifest.json")
        self.assertEqual(
            manifest["source_selective_eval_tree_sha256_before"],
            manifest["source_selective_eval_tree_sha256_after"],
        )
        self.assertEqual(manifest["source_selective_eval_tree_sha256_after"], tree_hash(self.eval_root / "eval"))

    def test_17_build_failure_is_atomic(self) -> None:
        name = self._unique("atomic_build")
        with mock.patch("enh3bench.generation_pilot.write_jsonl", side_effect=ValueError("injected")):
            with self.assertRaisesRegex(ValueError, "injected"):
                self._build(name)
        self.assertFalse((self.output_root / name).exists())
        self.assertFalse(any(path.name.startswith(f".{name}.staging_") for path in self.output_root.iterdir()))

    def test_18_clean_failure_preserves_existing_run(self) -> None:
        name = self._unique("rollback_build")
        run = self._build(name)
        original = read_json(run / "manifests/generation_run_manifest.json")
        with mock.patch("enh3bench.generation_pilot.write_jsonl", side_effect=ValueError("injected")):
            with self.assertRaisesRegex(ValueError, "injected"):
                self._build(name, clean=True)
        self.assertEqual(read_json(run / "manifests/generation_run_manifest.json"), original)

    def test_19_prompt_template_hash_is_bound(self) -> None:
        manifest = read_json(self._baseline() / "manifests/generation_run_manifest.json")
        from enh3bench.e2e_eval_schema import sha256_file
        self.assertEqual(manifest["prompt_template_sha256"], sha256_file(DEFAULT_PROMPT_TEMPLATE))

    def test_20_compiles_seven_prompt_instances(self) -> None:
        rows = read_jsonl(self._baseline() / "prompts/compiled_prompt_instances.jsonl")
        self.assertEqual(len(rows), PILOT_CASE_COUNT)

    def test_21_compiled_prompt_field_set_is_exact(self) -> None:
        rows = read_jsonl(self._baseline() / "prompts/compiled_prompt_instances.jsonl")
        self.assertTrue(all(set(row) == COMPILED_PROMPT_FIELDS for row in rows))

    def test_22_compiled_prompt_ids_are_stable(self) -> None:
        first = read_jsonl(self._baseline() / "prompts/compiled_prompt_instances.jsonl")
        name = self._unique("prompt_repro")
        run = self._build(name)
        prepare_generation_prompts(generation_run_name=name, generation_root=self.output_root)
        second = read_jsonl(run / "prompts/compiled_prompt_instances.jsonl")
        self.assertEqual(
            [row["prompt_instance_id"] for row in first],
            [row["prompt_instance_id"] for row in second],
        )

    def test_23_compiled_prompt_hash_changes_on_question_tamper(self) -> None:
        row = deepcopy(read_jsonl(self._baseline() / "prompts/compiled_prompt_instances.jsonl")[0])
        original = row["compiled_prompt_sha256"]
        row["question"] += " changed"
        base = {key: value for key, value in row.items() if key != "compiled_prompt_sha256"}
        from enh3bench.e2e_eval_schema import canonical_json, sha256_bytes
        changed = sha256_bytes(canonical_json(base).encode("utf-8"))
        self.assertNotEqual(original, changed)

    def test_24_compiled_prompt_has_response_schema(self) -> None:
        rows = read_jsonl(self._baseline() / "prompts/compiled_prompt_instances.jsonl")
        self.assertTrue(all(row["response_json_schema"] == RESPONSE_JSON_SCHEMA for row in rows))
        self.assertFalse(RESPONSE_JSON_SCHEMA["additionalProperties"])

    def test_25_compiled_prompts_have_metadata_firewall(self) -> None:
        rows = read_jsonl(self._baseline() / "prompts/compiled_prompt_instances.jsonl")
        self.assertTrue(all(not (set(row) & EVALUATOR_ONLY_FIELDS) for row in rows))

    def test_26_backend_satisfies_protocol(self) -> None:
        self.assertIsInstance(FixtureGenerationBackend(), GenerationBackend)

    def test_27_fixture_backend_identity(self) -> None:
        backend = FixtureGenerationBackend()
        self.assertEqual(backend.backend_name, "fixture")
        self.assertTrue(backend.backend_version)

    def test_28_unsupported_backend_is_rejected(self) -> None:
        for name in ("openai", "anthropic", "gemini", "azure", "remote", "real"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "real_api_backend_not_enabled"):
                    get_generation_backend(name)

    def test_29_cli_reports_unsupported_backend_contract(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = dry_run_cli.main([
                "--generation-run-name", self.baseline_name,
                "--pilot-root", str(self.output_root),
                "--backend", "openai",
            ])
        self.assertEqual(code, 1)
        self.assertIn("real_api_backend_not_enabled", stderr.getvalue())

    def test_30_request_envelopes_are_seven_and_exact(self) -> None:
        rows = read_jsonl(self._baseline() / "execution/request_envelopes.jsonl")
        self.assertEqual(len(rows), PILOT_CASE_COUNT)
        self.assertTrue(all(set(row) == REQUEST_ENVELOPE_FIELDS for row in rows))

    def test_31_receipts_are_seven_and_exact(self) -> None:
        rows = read_jsonl(self._baseline() / "execution/dry_run_receipts.jsonl")
        self.assertEqual(len(rows), PILOT_CASE_COUNT)
        self.assertTrue(all(set(row) == RECEIPT_FIELDS for row in rows))

    def test_32_receipts_are_nonimportable_dry_run_only(self) -> None:
        rows = read_jsonl(self._baseline() / "execution/dry_run_receipts.jsonl")
        self.assertTrue(all(row["execution_status"] == "dry_run" for row in rows))
        self.assertTrue(all(row["network_call_performed"] is False for row in rows))
        self.assertTrue(all(row["model_output_generated"] is False for row in rows))
        self.assertTrue(all(row["importable_api_output"] is False for row in rows))

    def test_33_receipts_contain_no_scientific_output_fields(self) -> None:
        forbidden = {"answer_text", "claims", "citations", "answer_status", "api_output_id", "token_usage"}
        rows = read_jsonl(self._baseline() / "execution/dry_run_receipts.jsonl")
        self.assertTrue(all(not (set(row) & forbidden) for row in rows))

    def test_34_request_hashes_link_receipts(self) -> None:
        envelopes = {row["case_id"]: row for row in read_jsonl(self._baseline() / "execution/request_envelopes.jsonl")}
        for receipt in read_jsonl(self._baseline() / "execution/dry_run_receipts.jsonl"):
            self.assertEqual(receipt["request_sha256"], envelopes[receipt["case_id"]]["request_sha256"])

    def test_35_dry_run_failure_writes_no_partial_execution_artifacts(self) -> None:
        name = self._unique("atomic_dry")
        run = self._build(name)
        prepare_generation_prompts(generation_run_name=name, generation_root=self.output_root)
        with self.assertRaisesRegex(ValueError, "injected_failure"):
            run_generation_dry_run(
                generation_run_name=name, generation_root=self.output_root,
                backend=ExplodingFixtureBackend(),
            )
        self.assertFalse((run / "execution/request_envelopes.jsonl").exists())
        self.assertFalse((run / "execution/dry_run_receipts.jsonl").exists())

    def test_36_no_network_primitive_is_used(self) -> None:
        name = self._unique("no_network")
        run = self._build(name)
        prepare_generation_prompts(generation_run_name=name, generation_root=self.output_root)
        with mock.patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            result = run_generation_dry_run(generation_run_name=name, generation_root=self.output_root)
        self.assertEqual(result["network_call_count"], 0)
        self.assertFalse((run / "outputs/api_outputs.jsonl").exists())

    def test_37_b1b0_source_has_no_credential_or_transport_surface(self) -> None:
        text = (ROOT / "enh3bench/generation_pilot.py").read_text(encoding="utf-8")
        forbidden = (
            "OpenAI" + "CompatibleClient", "authorize" + "-real-api", "api-key" + "-env",
            "LLM_" + "API_KEY", "LLM_" + "BASE_URL", "LLM_" + "MODEL", "UST" + "C_",
            "os." + "environ", "get" + "env", "http" + "x", "aio" + "http",
        )
        self.assertTrue(all(value not in text for value in forbidden))

    def test_38_token_only_estimate_has_null_costs(self) -> None:
        value = read_json(self._baseline() / "reports/cost_estimate_template.json")
        self.assertEqual(value["estimate_status"], "token_only")
        for field in (
            "pricing_input_per_million", "pricing_output_per_million",
            "estimated_cost_lower", "estimated_cost_upper",
        ):
            self.assertIsNone(value[field])

    def test_39_token_estimate_has_required_positive_counts(self) -> None:
        value = read_json(self._baseline() / "reports/token_estimate.json")
        self.assertEqual(value["case_count"], PILOT_CASE_COUNT)
        self.assertGreater(value["prompt_character_count"], 0)
        self.assertGreater(value["estimated_input_tokens_upper"], value["estimated_input_tokens_lower"])
        self.assertEqual(value["estimated_total_output_tokens"], 7 * 1200)

    def test_40_priced_estimate_uses_only_explicit_values(self) -> None:
        name = self._unique("priced")
        run = self._build(name)
        prepare_generation_prompts(generation_run_name=name, generation_root=self.output_root)
        result = estimate_generation_cost(
            generation_run_name=name, generation_root=self.output_root,
            pricing_input_per_million=2.5, pricing_output_per_million=10.0,
            currency="USD", pricing_source="fixture schedule", pricing_as_of="2026-07-22",
        )
        value = result["cost_estimate"]
        self.assertEqual(value["estimate_status"], "priced")
        self.assertGreaterEqual(value["estimated_cost_upper"], value["estimated_cost_lower"])
        self.assertEqual(read_json(run / "reports/cost_estimate_template.json"), value)

    def test_41_negative_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_input_price"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=-1, pricing_output_per_million=1,
                currency="USD", pricing_source="fixture", pricing_as_of="2026-07-22",
            )

    def test_42_nan_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_input_price"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=math.nan, pricing_output_per_million=1,
                currency="USD", pricing_source="fixture", pricing_as_of="2026-07-22",
            )

    def test_43_infinite_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_output_price"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=1, pricing_output_per_million=math.inf,
                currency="USD", pricing_source="fixture", pricing_as_of="2026-07-22",
            )

    def test_44_blank_currency_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "blank_currency"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=1, pricing_output_per_million=1,
                currency=" ", pricing_source="fixture", pricing_as_of="2026-07-22",
            )

    def test_45_blank_pricing_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "blank_pricing_source"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=1, pricing_output_per_million=1,
                currency="USD", pricing_source=" ", pricing_as_of="2026-07-22",
            )

    def test_46_invalid_pricing_date_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_pricing_date"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=1, pricing_output_per_million=1,
                currency="USD", pricing_source="fixture", pricing_as_of="2026-99-99",
            )

    def test_47_one_sided_pricing_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires_both"):
            estimate_generation_cost(
                generation_run_name=self.baseline_name, generation_root=self.output_root,
                pricing_input_per_million=1,
                currency="USD", pricing_source="fixture", pricing_as_of="2026-07-22",
            )

    def test_48_reproducibility_hashes_match_across_run_names(self) -> None:
        name_a = self._unique("repro_a")
        name_b = self._unique("repro_b")
        run_a = self._full(name_a)
        run_b = self._full(name_b)
        self.assertEqual(reproducibility_hashes(run_a), reproducibility_hashes(run_b))

    def test_49_normalization_does_not_hide_case_identity_change(self) -> None:
        name, run = self._copy_baseline("identity_tamper")
        path = run / "pilot/development_pilot_batch.jsonl"
        before = normalized_artifact_hash(path)
        rows = read_jsonl(path)
        rows[0]["case_id"] = "EC16_TAMPERED"
        write_jsonl(path, rows)
        self.assertNotEqual(before, normalized_artifact_hash(path), name)

    def test_50_validator_passes_complete_offline_pilot(self) -> None:
        result = validate_generation_pilot(
            generation_run_name=self.baseline_name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_51_validator_rejects_holdout_case_tamper(self) -> None:
        name, run = self._copy_baseline("holdout_tamper")
        selection_path = run / "pilot/pilot_selection_manifest.json"
        selection = read_json(selection_path)
        holdout = next(row for row in self._cases() if row["split"] == "holdout")
        selection["selected_cases"][0].update({
            "case_id": holdout["case_id"], "paper_id": holdout["paper_id"],
        })
        write_json(selection_path, selection)
        result = validate_generation_pilot(
            generation_run_name=name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("selection_not_reproducible" in error or "boundary" in error for error in result["errors"]))

    def test_52_validator_rejects_absolute_path_serialization(self) -> None:
        name, run = self._copy_baseline("path_tamper")
        path = run / "reports/cost_estimate_template.json"
        value = read_json(path)
        value["pricing_source"] = r"C:\private\price.txt"
        write_json(path, value)
        result = validate_generation_pilot(
            generation_run_name=name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertGreater(result["counts"]["absolute_paths"], 0)

    def test_53_validator_rejects_secret_serialization(self) -> None:
        name, run = self._copy_baseline("secret_tamper")
        path = run / "reports/cost_estimate_template.json"
        value = read_json(path)
        value["pricing_source"] = "api_key=secret"
        write_json(path, value)
        result = validate_generation_pilot(
            generation_run_name=name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertGreater(result["counts"]["secrets"], 0)

    def test_54_validator_rejects_evaluator_metadata_in_prompt(self) -> None:
        name, run = self._copy_baseline("metadata_tamper")
        path = run / "prompts/compiled_prompt_instances.jsonl"
        rows = read_jsonl(path)
        rows[0]["answerability_status"] = "answerable"
        write_jsonl(path, rows)
        result = validate_generation_pilot(
            generation_run_name=name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertGreater(result["counts"]["evaluator_metadata_in_generator_artifacts"], 0)

    def test_55_validator_rejects_missing_receipts(self) -> None:
        name, run = self._copy_baseline("missing_receipt")
        (run / "execution/dry_run_receipts.jsonl").unlink()
        result = validate_generation_pilot(
            generation_run_name=name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("missing_artifacts", result["errors"][0])

    def test_56_validator_rejects_api_output_artifact(self) -> None:
        name, run = self._copy_baseline("output_tamper")
        write_jsonl(run / "outputs/api_outputs.jsonl", [])
        result = validate_generation_pilot(
            generation_run_name=name, generation_root=self.output_root,
            selective_eval_root=self.eval_root, source_calibration_root=self.calibration_root,
            check_source_package=False,
        )
        self.assertGreater(result["counts"]["api_output_artifact_count"], 0)

    def test_57_source_selective_eval_remains_blank(self) -> None:
        result = validate_selective_eval_package(
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            source_calibration_root=self.calibration_root, check_source_package=False,
        )
        self.assertEqual(result["counts"]["package_stage"], "blank")
        self.assertEqual(result["counts"]["imported_api_output_count"], 0)
        self.assertEqual(result["counts"]["imported_machine_judgment_count"], 0)
        self.assertEqual(result["counts"]["human_labels_filled"], 0)

    def test_58_no_forbidden_later_phase_artifacts_exist(self) -> None:
        names = {path.name for path in self._baseline().rglob("*") if path.is_file()}
        self.assertFalse(any("freeze" in name for name in names))
        self.assertFalse(any("holdout_release" in name for name in names))
        self.assertFalse(any("machine_judgment" in name for name in names))
        self.assertFalse(any("human" in name for name in names))

    def test_59_execution_only_field_set_is_exact(self) -> None:
        self.assertEqual(EXECUTION_ONLY_FIELDS, {
            "generation_status", "network_call_performed", "execution_status",
            "model_output_generated", "importable_api_output", "backend_name",
            "backend_version", "execution_receipt_id", "created_at_utc",
        })

    def test_60_validator_rejects_generation_status_in_batch(self) -> None:
        name, run = self._copy_baseline("batch_generation_status")
        path = run / "pilot/development_pilot_batch.jsonl"
        rows = read_jsonl(path)
        rows[0]["generation_status"] = "pending"
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertGreater(result["counts"]["pilot_batch_unknown_field_count"], 0)
        self.assertGreater(result["counts"]["input_execution_state_field_count"], 0)

    def test_61_validator_rejects_network_state_in_batch(self) -> None:
        name, run = self._copy_baseline("batch_network_state")
        path = run / "pilot/development_pilot_batch.jsonl"
        rows = read_jsonl(path)
        rows[0]["network_call_performed"] = False
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertGreater(result["counts"]["input_execution_state_field_count"], 0)

    def test_62_validator_rejects_generation_status_in_compiled_source_payload(self) -> None:
        name, run = self._copy_baseline("prompt_generation_status")
        path = run / "prompts/compiled_prompt_instances.jsonl"
        rows = read_jsonl(path)
        rows[0]["bounded_source_context"][0]["generation_status"] = "pending"
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertGreater(result["counts"]["compiled_prompt_forbidden_execution_field_count"], 0)

    def test_63_validator_rejects_network_state_in_compiled_source_payload(self) -> None:
        name, run = self._copy_baseline("prompt_network_state")
        path = run / "prompts/compiled_prompt_instances.jsonl"
        rows = read_jsonl(path)
        rows[0]["bounded_source_context"][0]["network_call_performed"] = False
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertGreater(result["counts"]["input_execution_state_field_count"], 0)

    def test_64_validator_rejects_unknown_batch_field(self) -> None:
        name, run = self._copy_baseline("batch_unknown")
        path = run / "pilot/development_pilot_batch.jsonl"
        rows = read_jsonl(path)
        rows[0]["unexpected_field"] = "value"
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["counts"]["pilot_batch_unknown_field_count"], 1)

    def test_65_validator_rejects_receipt_missing_network_state(self) -> None:
        name, run = self._copy_baseline("receipt_missing_network")
        path = run / "execution/dry_run_receipts.jsonl"
        rows = read_jsonl(path)
        del rows[0]["network_call_performed"]
        write_jsonl(path, rows)
        self.assertEqual(self._validate(name)["result"], "FAIL")

    def test_66_validator_rejects_receipt_network_true(self) -> None:
        name, run = self._copy_baseline("receipt_network_true")
        path = run / "execution/dry_run_receipts.jsonl"
        rows = read_jsonl(path)
        rows[0]["network_call_performed"] = True
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["counts"]["network_call_count"], 1)

    def test_67_validator_rejects_receipt_model_output_true(self) -> None:
        name, run = self._copy_baseline("receipt_model_true")
        path = run / "execution/dry_run_receipts.jsonl"
        rows = read_jsonl(path)
        rows[0]["model_output_generated"] = True
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["counts"]["model_output_count"], 1)

    def test_68_validator_rejects_receipt_importable_output_true(self) -> None:
        name, run = self._copy_baseline("receipt_importable_true")
        path = run / "execution/dry_run_receipts.jsonl"
        rows = read_jsonl(path)
        rows[0]["importable_api_output"] = True
        write_jsonl(path, rows)
        result = self._validate(name)
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["counts"]["importable_output_count"], 1)

    def test_69_validator_counts_evaluator_fields_in_request_and_receipt(self) -> None:
        for relative, count_key in (
            ("execution/request_envelopes.jsonl", "request_envelope_forbidden_evaluator_field_count"),
            ("execution/dry_run_receipts.jsonl", "receipt_forbidden_evaluator_field_count"),
        ):
            with self.subTest(relative=relative):
                name, run = self._copy_baseline("execution_evaluator")
                path = run / relative
                rows = read_jsonl(path)
                rows[0]["answerability_status"] = "answerable"
                write_jsonl(path, rows)
                result = self._validate(name)
                self.assertEqual(result["result"], "FAIL")
                self.assertEqual(result["counts"][count_key], 1)

    def test_70_pilot_root_must_not_overlap_source_package(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlaps_source_package"):
            build_development_pilot(
                selective_eval_run_name="eval",
                selective_eval_root=self.eval_root,
                source_calibration_root=self.calibration_root,
                generation_run_name="overlap",
                generation_root=self.eval_root / "eval/runtime",
                validate_source_package=False,
            )

    def test_71_all_clis_accept_explicit_temporary_pilot_root(self) -> None:
        pilot_root = self.base / "explicit_cli_root"
        run_name = self._unique("explicit_cli")
        common = ["--pilot-root", str(pilot_root), "--generation-run-name", run_name]
        output = io.StringIO()
        source_pass = {
            "result": "PASS", "errors": [],
            "counts": {
                "package_stage": "blank", "imported_api_output_count": 0,
                "imported_machine_judgment_count": 0, "human_labels_filled": 0,
            },
        }
        with (
            mock.patch("enh3bench.generation_pilot.validate_selective_eval_package", return_value=source_pass),
            redirect_stdout(output),
        ):
            self.assertEqual(build_cli.main([
                *common,
                "--selective-eval-run-name", "eval",
                "--selective-eval-root", str(self.eval_root),
                "--source-calibration-root", str(self.calibration_root),
            ]), 0)
            self.assertEqual(prepare_cli.main(common), 0)
            self.assertEqual(dry_run_cli.main([*common, "--backend", "fixture"]), 0)
            self.assertEqual(estimate_cli.main(common), 0)
            self.assertEqual(check_cli.main([
                *common,
                "--selective-eval-root", str(self.eval_root),
                "--source-calibration-root", str(self.calibration_root),
            ]), 0)

    def test_72_cli_default_pilot_root_is_effective(self) -> None:
        pilot_root = self.base / "default_cli_root"
        run_name = self._unique("default_cli")
        output = io.StringIO()
        source_pass = {
            "result": "PASS", "errors": [],
            "counts": {
                "package_stage": "blank", "imported_api_output_count": 0,
                "imported_machine_judgment_count": 0, "human_labels_filled": 0,
            },
        }
        with (
            mock.patch.object(build_cli, "DEFAULT_PILOT_ROOT", pilot_root),
            mock.patch.object(prepare_cli, "DEFAULT_PILOT_ROOT", pilot_root),
            mock.patch.object(dry_run_cli, "DEFAULT_PILOT_ROOT", pilot_root),
            mock.patch.object(estimate_cli, "DEFAULT_PILOT_ROOT", pilot_root),
            mock.patch.object(check_cli, "DEFAULT_PILOT_ROOT", pilot_root),
            mock.patch("enh3bench.generation_pilot.validate_selective_eval_package", return_value=source_pass),
            redirect_stdout(output),
        ):
            self.assertEqual(build_cli.main([
                "--generation-run-name", run_name,
                "--selective-eval-run-name", "eval",
                "--selective-eval-root", str(self.eval_root),
                "--source-calibration-root", str(self.calibration_root),
            ]), 0)
            self.assertEqual(prepare_cli.main(["--generation-run-name", run_name]), 0)
            self.assertEqual(dry_run_cli.main([
                "--generation-run-name", run_name, "--backend", "fixture",
            ]), 0)
            self.assertEqual(estimate_cli.main(["--generation-run-name", run_name]), 0)
            self.assertEqual(check_cli.main([
                "--generation-run-name", run_name,
                "--selective-eval-root", str(self.eval_root),
                "--source-calibration-root", str(self.calibration_root),
            ]), 0)

    def test_73_serialized_artifacts_do_not_record_pilot_root(self) -> None:
        serialized = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self._baseline().rglob("*")
            if path.is_file() and path.suffix in {".json", ".jsonl"}
        )
        self.assertNotIn(str(self.output_root), serialized)

    def test_74_core_module_has_no_drive_specific_default_root(self) -> None:
        text = (ROOT / "enh3bench/generation_pilot.py").read_text(encoding="utf-8")
        self.assertNotIn("eNH3_Bench_API", text)


if __name__ == "__main__":
    unittest.main()
