from __future__ import annotations

import copy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

from enh3bench.design_compiler_v018 import (
    CRITIC_RESULT_SCHEMA_VERSION,
    DESIGN_CARD_SCHEMA_VERSION,
    DESIGN_PROBLEM_SCHEMA_VERSION,
    GATE_TYPES,
    MISSING_INPUT_SPECS,
    OBJECTIVE_DEFINITIONS,
    SCHEMA_FILENAMES,
    VARIABLE_DEFINITIONS,
    build_linnr_design_problem,
    canonical_json_bytes,
    compare_output_trees,
    content_sha256,
    design_space_inventory,
    deterministic_critics,
    load_schema,
    make_critic_result,
    make_fixture_card,
    make_simulation_job,
    missing_input_inventory,
    render_inventory_html,
    route_simulation,
    stable_id,
    validate_critic_result,
    validate_design_card,
    validate_design_problem,
    validate_simulation_job,
    with_content_hash,
    write_runtime_outputs,
)


COMMIT = "1" * 40
FAMILIES = ("LiNRR", "eNRR", "NO3RR", "NO2RR", "unclear", "NO3RR", "eNRR", "unclear", "NORR", "mixed", "eNRR", "NO3RR")


def write_a1_runtime(root: Path) -> Path:
    rows = []
    paper_ids = ("P0797", "P0425", "P0162", "P0255", "P0471", "P0217", "P0362", "P0007", "P0961", "P0241", "P0960", "P0312")
    for index, (paper_id, family) in enumerate(zip(paper_ids, FAMILIES), start=1):
        rows.append({
            "paper_id": paper_id,
            "package_id": f"EP18_{index:024X}",
            "package_path": f"packages/{paper_id}/evidence_package.json",
            "reaction_family_coverage": [family],
            "review_status": "machine_drafted",
            "content_sha256": f"{index:064x}",
            "evidence_link_count": 0 if paper_id in {"P0797", "P0312"} else index,
            "validation_result": "PASS",
        })
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "v018_a1_package_index.json").write_text(
        json.dumps({"schema_version": "0.18-evidence-package.1", "packages": rows}), encoding="utf-8",
    )
    package_dir = root / "packages" / "P0797"
    package_dir.mkdir(parents=True)
    package = {
        "source_documents": [
            {"document_type": "main", "availability_status": "available"},
            {"document_type": "supplementary", "availability_status": "not_reported"},
        ],
        "experiment_records": [{
            "measurements": {
                "reaction_family": {"status": "reported", "value": "LiNRR"},
                "electrolyte": {"status": "not_reported"},
                "current_density_ma_cm2": {"status": "not_reported"},
                "blank_control": {"status": "reported", "value": "unclear"},
                "isotope_validation": {"status": "reported", "value": "unclear"},
            }
        }],
    }
    (package_dir / "evidence_package.json").write_text(json.dumps(package), encoding="utf-8")
    return root


def rehash(value: dict) -> dict:
    value["content_hash"] = content_sha256(value)
    return value


def problem_fixture() -> tuple[tempfile.TemporaryDirectory[str], dict]:
    temp = tempfile.TemporaryDirectory()
    root = write_a1_runtime(Path(temp.name))
    return temp, build_linnr_design_problem(root, COMMIT)


def critic_codes(card: dict, **kwargs) -> set[str]:
    return {row["finding_code"] for row in deterministic_critics(card, **kwargs)}


def assignment(card: dict, name: str) -> dict:
    return next(row for row in card["decision_variables"] if row["name"] == name)


class DesignProblemContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp, self.problem = problem_fixture()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_01_valid_design_problem(self) -> None:
        self.assertEqual(validate_design_problem(self.problem)["result"], "PASS")

    def test_02_invalid_reaction_family(self) -> None:
        value = copy.deepcopy(self.problem)
        value["reaction_family"] = "OTHER"
        rehash(value)
        self.assertEqual(validate_design_problem(value)["result"], "FAIL")

    def test_03_duplicate_variable_ids_fail(self) -> None:
        value = copy.deepcopy(self.problem)
        value["decision_variables"][1]["variable_id"] = value["decision_variables"][0]["variable_id"]
        rehash(value)
        self.assertTrue(any("duplicate variable IDs" in item for item in validate_design_problem(value)["errors"]))

    def test_04_invalid_units_fail(self) -> None:
        value = copy.deepcopy(self.problem)
        value["decision_variables"][0]["unit"] = "made_up_unit"
        rehash(value)
        self.assertTrue(any("unit allowlist" in item for item in validate_design_problem(value)["errors"]))

    def test_05_numeric_bounds_are_accepted(self) -> None:
        value = copy.deepcopy(self.problem)
        variable = next(row for row in value["decision_variables"] if row["name"] == "water_content_ppm")
        variable.update({"numeric_bounds": {"minimum": 0, "maximum": 100, "minimum_inclusive": True, "maximum_inclusive": True}, "nominal_value": 10, "source_status": "assumed"})
        rehash(value)
        self.assertEqual(validate_design_problem(value)["result"], "PASS")

    def test_06_inverted_numeric_bounds_fail(self) -> None:
        value = copy.deepcopy(self.problem)
        variable = next(row for row in value["decision_variables"] if row["name"] == "water_content_ppm")
        variable["numeric_bounds"] = {"minimum": 100, "maximum": 0, "minimum_inclusive": True, "maximum_inclusive": True}
        rehash(value)
        self.assertTrue(any("inverted" in item for item in validate_design_problem(value)["errors"]))

    def test_07_categorical_allowed_values_are_accepted(self) -> None:
        value = copy.deepcopy(self.problem)
        variable = next(row for row in value["decision_variables"] if row["name"] == "cell_type")
        variable.update({"allowed_values": ["FIXTURE_A", "FIXTURE_B"], "nominal_value": "FIXTURE_A", "source_status": "assumed"})
        rehash(value)
        self.assertEqual(validate_design_problem(value)["result"], "PASS")

    def test_08_nominal_outside_allowed_values_fails(self) -> None:
        value = copy.deepcopy(self.problem)
        variable = next(row for row in value["decision_variables"] if row["name"] == "cell_type")
        variable.update({"allowed_values": ["FIXTURE_A"], "nominal_value": "FIXTURE_B", "source_status": "assumed"})
        rehash(value)
        self.assertTrue(any("outside allowed_values" in item for item in validate_design_problem(value)["errors"]))

    def test_09_reported_value_requires_evidence(self) -> None:
        value = copy.deepcopy(self.problem)
        value["decision_variables"][0].update({"source_status": "reported", "nominal_value": "FIXTURE", "evidence_refs": []})
        rehash(value)
        self.assertTrue(any("reported values require" in item for item in validate_design_problem(value)["errors"]))

    def test_10_assumed_value_is_visibly_labelled_and_valid(self) -> None:
        value = copy.deepcopy(self.problem)
        value["decision_variables"][0].update({"source_status": "assumed", "nominal_value": "FIXTURE"})
        rehash(value)
        self.assertEqual(validate_design_problem(value)["result"], "PASS")

    def test_11_assumed_value_cannot_be_implicit(self) -> None:
        value = copy.deepcopy(self.problem)
        value["decision_variables"][0]["source_status"] = "assumed"
        rehash(value)
        self.assertTrue(any("assumed value must be explicit" in item for item in validate_design_problem(value)["errors"]))

    def test_12_unknown_value_cannot_have_nominal_fact(self) -> None:
        value = copy.deepcopy(self.problem)
        value["decision_variables"][0]["nominal_value"] = "INVENTED"
        rehash(value)
        self.assertTrue(any("must not invent" in item for item in validate_design_problem(value)["errors"]))

    def test_13_hard_constraint_type_is_enforced(self) -> None:
        value = copy.deepcopy(self.problem)
        value["hard_constraints"][0]["constraint_type"] = "soft"
        rehash(value)
        self.assertTrue(any("constraint_type=hard" in item for item in validate_design_problem(value)["errors"]))

    def test_14_soft_constraint_type_is_enforced(self) -> None:
        value = copy.deepcopy(self.problem)
        value["soft_constraints"][0]["constraint_type"] = "hard"
        rehash(value)
        self.assertTrue(any("constraint_type=soft" in item for item in validate_design_problem(value)["errors"]))

    def test_15_multi_objective_preservation(self) -> None:
        self.assertEqual([row["name"] for row in self.problem["objectives"]], [row[0] for row in OBJECTIVE_DEFINITIONS])

    def test_16_no_fabricated_aggregate_score(self) -> None:
        text = json.dumps(self.problem).casefold()
        self.assertNotIn("aggregate_score", text)

    def test_17_content_hash_is_checked(self) -> None:
        value = copy.deepcopy(self.problem)
        value["content_hash"] = "0" * 64
        self.assertTrue(any("content_hash mismatch" in item for item in validate_design_problem(value)["errors"]))

    def test_18_design_problem_id_is_deterministic(self) -> None:
        self.assertEqual(self.problem["design_problem_id"], stable_id("DP18", DESIGN_PROBLEM_SCHEMA_VERSION, self.problem["reaction_family"], self.problem["scientific_objective"]))

    def test_19_canonical_bytes_are_deterministic(self) -> None:
        reordered = dict(reversed(list(self.problem.items())))
        self.assertEqual(canonical_json_bytes(self.problem), canonical_json_bytes(reordered))

    def test_20_schema_fails_closed(self) -> None:
        value = copy.deepcopy(self.problem)
        value["unexpected"] = True
        rehash(value)
        self.assertEqual(validate_design_problem(value)["result"], "FAIL")

    def test_21_absolute_paths_are_rejected(self) -> None:
        value = copy.deepcopy(self.problem)
        value["provenance"]["source_refs"][0] = "C:/private/file.json"
        rehash(value)
        self.assertTrue(any("absolute path" in item or "does not match" in item for item in validate_design_problem(value)["errors"]))

    def test_22_secret_fields_are_rejected(self) -> None:
        value = copy.deepcopy(self.problem)
        value["credential"] = "fixture"
        rehash(value)
        self.assertTrue(any("forbidden field" in item for item in validate_design_problem(value)["errors"]))

    def test_23_reasoning_fields_are_rejected(self) -> None:
        value = copy.deepcopy(self.problem)
        value["model_reasoning"] = "fixture"
        rehash(value)
        self.assertTrue(any("forbidden field" in item for item in validate_design_problem(value)["errors"]))

    def test_24_hidden_labels_are_rejected(self) -> None:
        value = copy.deepcopy(self.problem)
        value["hidden_labels"] = []
        rehash(value)
        self.assertTrue(any("forbidden field" in item for item in validate_design_problem(value)["errors"]))

    def test_25_cross_family_direct_support_fails(self) -> None:
        value = copy.deepcopy(self.problem)
        value["evidence_package_refs"][1]["cross_family_role"] = "direct_design_evidence"
        rehash(value)
        self.assertTrue(any("cross-family" in item for item in validate_design_problem(value)["errors"]))

    def test_26_only_p0797_is_direct_linnr_evidence(self) -> None:
        direct = [row["paper_id"] for row in self.problem["evidence_package_refs"] if row["cross_family_role"] == "direct_design_evidence"]
        self.assertEqual(direct, ["P0797"])

    def test_27_five_human_gates_are_defined(self) -> None:
        self.assertEqual({row["gate_type"] for row in self.problem["human_gate_policy"]}, set(GATE_TYPES))

    def test_28_compiler_does_not_fabricate_approval(self) -> None:
        value = copy.deepcopy(self.problem)
        value["human_gate_policy"][0].update({"status": "approved", "decision": "approve"})
        rehash(value)
        self.assertTrue(any("fabricate" in item for item in validate_design_problem(value)["errors"]))

    def test_29_variable_ontology_covers_all_required_names(self) -> None:
        expected = {name for records in VARIABLE_DEFINITIONS.values() for name, _, _ in records}
        self.assertEqual({row["name"] for row in self.problem["decision_variables"]}, expected)

    def test_30_each_variable_has_cost_safety_and_uncertainty(self) -> None:
        for variable in self.problem["decision_variables"]:
            self.assertIn("cost_class", variable)
            self.assertIn("safety_class", variable)
            self.assertIn("uncertainty", variable)


class InventoryAndRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.a1 = write_a1_runtime(Path(self.temp.name) / "a1")
        self.problem = build_linnr_design_problem(self.a1, COMMIT)
        self.rows = missing_input_inventory(self.problem, self.a1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_31_all_required_missing_inputs_are_audited(self) -> None:
        self.assertEqual({row["input_id"] for row in self.rows}, {row[0] for row in MISSING_INPUT_SPECS})

    def test_32_missing_values_are_not_invented(self) -> None:
        row = next(item for item in self.rows if item["input_id"] == "water_content_coverage")
        self.assertEqual((row["status"], row["observed_state"]), ("missing", "not_reported"))

    def test_33_training_corpus_is_explicitly_insufficient(self) -> None:
        inventory = design_space_inventory(self.problem, self.rows)
        self.assertFalse(inventory["linnr_training_corpus_sufficient"])
        self.assertEqual(inventory["direct_linnr_package_count"], 1)

    def test_34_inventory_contains_no_candidates_or_recommendations(self) -> None:
        inventory = design_space_inventory(self.problem, self.rows)
        self.assertEqual((inventory["candidate_count"], inventory["recommendation_count"]), (0, 0))

    def test_35_html_is_deterministic(self) -> None:
        inventory = design_space_inventory(self.problem, self.rows)
        self.assertEqual(render_inventory_html(inventory, self.rows), render_inventory_html(inventory, self.rows))

    def test_36_html_is_self_contained(self) -> None:
        html = render_inventory_html(design_space_inventory(self.problem, self.rows), self.rows).casefold()
        self.assertNotIn("<script", html)
        self.assertNotIn("src=", html)
        self.assertNotIn("href=", html)
        self.assertNotIn("@import", html)

    def test_37_runtime_layout_and_outputs(self) -> None:
        runtime = Path(self.temp.name) / "runtime"
        result = write_runtime_outputs(runtime, Path.cwd(), self.a1, COMMIT)
        self.assertEqual(result["result"], "PASS")
        for directory in ("inputs", "problems", "cards", "critics", "simulations", "reports", "logs"):
            self.assertTrue((runtime / directory).is_dir())
        self.assertTrue((runtime / "problems" / "linnr_discovery_problem.json").is_file())
        self.assertTrue((runtime / "reports" / "linnr_missing_inputs.csv").is_file())

    def test_38_two_runtime_roots_are_byte_identical(self) -> None:
        left, right = Path(self.temp.name) / "left", Path(self.temp.name) / "right"
        write_runtime_outputs(left, Path.cwd(), self.a1, COMMIT)
        write_runtime_outputs(right, Path.cwd(), self.a1, COMMIT)
        self.assertEqual(compare_output_trees(left, right)["result"], "PASS")

    def test_39_runtime_inside_repository_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            write_runtime_outputs(Path.cwd() / "runtime_forbidden", Path.cwd(), self.a1, COMMIT)

    def test_40_no_simulator_run_is_recorded(self) -> None:
        result = write_runtime_outputs(Path(self.temp.name) / "runtime", Path.cwd(), self.a1, COMMIT)
        self.assertEqual(result["simulator_runs"], {"COMSOL": 0, "DFT": 0, "MD": 0})


class DesignCardAndCriticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = make_fixture_card(code_commit=COMMIT)

    def test_41_fixture_card_validates(self) -> None:
        self.assertEqual(validate_design_card(self.card)["result"], "PASS")

    def test_42_fixture_card_is_explicitly_labelled(self) -> None:
        self.assertEqual(self.card["artifact_label"], "NON_SCIENTIFIC_FIXTURE")

    def test_43_tracked_fixture_directory_contains_no_real_card(self) -> None:
        fixture_root = Path("tests/fixtures/v018_design_compiler")
        for path in fixture_root.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("NON_SCIENTIFIC_FIXTURE", text)

    def test_44_missing_falsification_criterion_blocks_executable_card(self) -> None:
        value = copy.deepcopy(self.card)
        value["artifact_label"] = "EXECUTABLE_DESIGN"
        value["falsification_criteria"] = []
        value["provenance"]["generated_by"] = "human_configuration"
        rehash(value)
        self.assertTrue(any("falsification" in item for item in validate_design_card(value)["errors"]))

    def test_45_unspecified_required_variable_blocks_executable_card(self) -> None:
        value = copy.deepcopy(self.card)
        value["artifact_label"] = "EXECUTABLE_DESIGN"
        value["provenance"]["generated_by"] = "human_configuration"
        rehash(value)
        self.assertTrue(any("required variable" in item for item in validate_design_card(value)["errors"]))

    def test_46_failed_hard_constraint_blocks_executable_card(self) -> None:
        value = copy.deepcopy(self.card)
        value["artifact_label"] = "EXECUTABLE_DESIGN"
        value["provenance"]["generated_by"] = "human_configuration"
        value["constraints"][0]["status"] = "fail"
        for item in value["decision_variables"]:
            if item["value"] is None:
                item.update({"value": 1, "source_status": "assumed"})
        rehash(value)
        self.assertTrue(any("hard constraint" in item for item in validate_design_card(value)["errors"]))

    def test_47_rejected_safety_gate_blocks_executable_card(self) -> None:
        value = copy.deepcopy(self.card)
        value["artifact_label"] = "EXECUTABLE_DESIGN"
        value["provenance"]["generated_by"] = "human_configuration"
        for item in value["decision_variables"]:
            if item["value"] is None:
                item.update({"value": 1, "source_status": "assumed"})
        next(gate for gate in value["human_gates"] if gate["gate_type"] == "GATE_EXPERIMENT_SAFETY")["status"] = "rejected"
        rehash(value)
        self.assertTrue(any("safety gate" in item for item in validate_design_card(value)["errors"]))

    def test_48_unknown_water_content_warns(self) -> None:
        self.assertIn("LINRR_WATER_CONTENT_UNKNOWN", critic_codes(self.card, code_commit=COMMIT))

    def test_49_proton_donor_without_concentration_fails(self) -> None:
        self.assertIn("PROTON_DONOR_CONCENTRATION_MISSING", critic_codes(self.card, code_commit=COMMIT))

    def test_50_current_density_without_area_fails(self) -> None:
        self.assertIn("CURRENT_DENSITY_AREA_MISSING", critic_codes(self.card, code_commit=COMMIT))

    def test_51_flow_without_geometry_fails(self) -> None:
        value = copy.deepcopy(self.card)
        value["decision_variables"].append({
            "variable_id": stable_id("DV18", DESIGN_PROBLEM_SCHEMA_VERSION, "electrochemical_operation", "gas_flow_rate"),
            "name": "gas_flow_rate", "value": 1, "unit": "mL min^-1", "source_status": "assumed", "required": True,
            "evidence_refs": ["FIXTURE:SYNTHETIC"], "uncertainty": {"method": "not_available", "lower": None, "upper": None, "notes": "fixture"},
        })
        self.assertIn("FLOW_GEOMETRY_MISSING", critic_codes(value, code_commit=COMMIT))

    def test_52_pressure_without_rating_fails(self) -> None:
        value = copy.deepcopy(self.card)
        value["decision_variables"].append({
            "variable_id": stable_id("DV18", DESIGN_PROBLEM_SCHEMA_VERSION, "electrochemical_operation", "pressure"),
            "name": "pressure", "value": 1, "unit": "bar", "source_status": "assumed", "required": True,
            "evidence_refs": ["FIXTURE:SYNTHETIC"], "uncertainty": {"method": "not_available", "lower": None, "upper": None, "notes": "fixture"},
        })
        self.assertIn("PRESSURE_RATING_MISSING", critic_codes(value, code_commit=COMMIT))

    def test_53_context_only_evidence_warns(self) -> None:
        value = copy.deepcopy(self.card)
        value["evidence_for"] = ["CTX:FIXTURE"]
        self.assertIn("CONTEXT_ONLY_SUPPORT", critic_codes(value, code_commit=COMMIT))

    def test_54_missing_ammonia_controls_fails(self) -> None:
        value = copy.deepcopy(self.card)
        value["required_controls"] = []
        self.assertIn("NH3_CONTROLS_MISSING", critic_codes(value, code_commit=COMMIT))

    def test_55_lab_capability_violation_fails(self) -> None:
        temp, problem = problem_fixture()
        try:
            value = copy.deepcopy(self.card)
            value["required_controls"].append("isotope_controls")
            self.assertIn("LAB_CAPABILITY_VIOLATION", critic_codes(value, problem=problem, code_commit=COMMIT))
        finally:
            temp.cleanup()

    def test_56_critic_blocking_semantics(self) -> None:
        results = deterministic_critics(self.card, code_commit=COMMIT)
        self.assertTrue(all(row["blocking"] == (row["verdict"] == "fail") for row in results))

    def test_57_critic_result_validates(self) -> None:
        result = make_critic_result("evidence_critic", self.card["design_id"], "warning", "medium", "FIXTURE_WARNING", "Synthetic visible warning.", "Resolve synthetic fixture.", code_commit=COMMIT)
        self.assertEqual(validate_critic_result(result)["result"], "PASS")

    def test_58_nonblocking_fail_critic_is_rejected(self) -> None:
        result = make_critic_result("evidence_critic", self.card["design_id"], "fail", "high", "FIXTURE_FAIL", "Synthetic visible failure.", "Resolve synthetic fixture.", code_commit=COMMIT)
        result["blocking"] = False
        self.assertEqual(validate_critic_result(result)["result"], "FAIL")


class SimulationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = make_fixture_card(code_commit=COMMIT)

    def test_59_comsol_target_routes_to_comsol(self) -> None:
        self.assertEqual(route_simulation(self.card["design_id"], "Fixture question", "fluid_flow", code_commit=COMMIT)["simulation_type"], "COMSOL")

    def test_60_dft_target_routes_to_dft(self) -> None:
        self.assertEqual(route_simulation(self.card["design_id"], "Fixture question", "adsorption", code_commit=COMMIT)["simulation_type"], "DFT")

    def test_61_md_target_routes_to_md(self) -> None:
        self.assertEqual(route_simulation(self.card["design_id"], "Fixture question", "solvation_structure", code_commit=COMMIT)["simulation_type"], "MD")

    def test_62_unknown_target_requires_human(self) -> None:
        self.assertEqual(route_simulation(self.card["design_id"], "Fixture question", "unknown_target", code_commit=COMMIT)["simulation_type"], "human_required")

    def test_63_comsol_without_boundaries_is_critic_failure(self) -> None:
        job = route_simulation(self.card["design_id"], "Fixture question", "fluid_flow", code_commit=COMMIT)
        self.assertIn("COMSOL_INPUTS_INCOMPLETE", critic_codes(self.card, simulation_jobs=[job], code_commit=COMMIT))

    def test_64_dft_without_structure_is_critic_failure(self) -> None:
        job = route_simulation(self.card["design_id"], "Fixture question", "adsorption", code_commit=COMMIT)
        self.assertIn("DFT_STRUCTURE_MISSING", critic_codes(self.card, simulation_jobs=[job], code_commit=COMMIT))

    def test_65_md_without_force_field_is_critic_failure(self) -> None:
        job = route_simulation(self.card["design_id"], "Fixture question", "solvation_structure", code_commit=COMMIT)
        self.assertIn("MD_FORCE_FIELD_MISSING", critic_codes(self.card, simulation_jobs=[job], code_commit=COMMIT))

    def test_66_expensive_job_requires_human_gate(self) -> None:
        job = route_simulation(self.card["design_id"], "Fixture question", "adsorption", code_commit=COMMIT)
        self.assertTrue(job["human_gate_required"])
        self.assertEqual(validate_simulation_job(job)["result"], "PASS")

    def test_67_compiler_cannot_approve_simulation_job(self) -> None:
        job = route_simulation(self.card["design_id"], "Fixture question", "adsorption", code_commit=COMMIT)
        job["status"] = "approved"
        self.assertTrue(any("cannot approve" in item for item in validate_simulation_job(job)["errors"]))

    def test_68_simulation_schema_fails_closed(self) -> None:
        job = route_simulation(self.card["design_id"], "Fixture question", "adsorption", code_commit=COMMIT)
        job["unexpected"] = True
        self.assertEqual(validate_simulation_job(job)["result"], "FAIL")


class SafetyAndSchemaTests(unittest.TestCase):
    def test_69_all_schemas_are_draft_2020_12(self) -> None:
        for kind in SCHEMA_FILENAMES:
            schema = load_schema(kind)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            Draft202012Validator.check_schema(schema)

    def test_70_all_schema_objects_fail_closed(self) -> None:
        def visit(value: object) -> None:
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(value.get("additionalProperties"), False)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        for kind in SCHEMA_FILENAMES:
            visit(load_schema(kind))

    def test_71_library_has_no_f_drive_dependency(self) -> None:
        source = Path("enh3bench/design_compiler_v018.py").read_text(encoding="utf-8")
        self.assertNotIn("F:" + "\\", source)

    def test_72_library_does_not_access_credentials(self) -> None:
        source = Path("enh3bench/design_compiler_v018.py").read_text(encoding="utf-8")
        self.assertNotIn("os." + "environ", source)
        self.assertNotIn("get" + "env(", source)

    def test_73_compiler_does_not_use_network(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            a1 = write_a1_runtime(Path(name))
            with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
                problem = build_linnr_design_problem(a1, COMMIT)
        self.assertEqual(problem["reaction_family"], "LiNRR")

    def test_74_no_model_or_simulator_modules_are_imported(self) -> None:
        source = Path("enh3bench/design_compiler_v018.py").read_text(encoding="utf-8").casefold()
        self.assertNotIn("openai", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("requests", source)

    def test_75_stable_ids_ignore_json_formatting(self) -> None:
        left = stable_id("DV18", {"a": 1, "b": 2})
        right = stable_id("DV18", {"b": 2, "a": 1})
        self.assertEqual(left, right)

    def test_76_incompatible_card_and_problem_ranges_are_blocking(self) -> None:
        temp, problem = problem_fixture()
        try:
            definition = next(row for row in problem["decision_variables"] if row["name"] == "current_density")
            definition["numeric_bounds"] = {"minimum": 0, "maximum": 0.5, "minimum_inclusive": True, "maximum_inclusive": True}
            rehash(problem)
            card = make_fixture_card(code_commit=COMMIT)
            self.assertIn("INCOMPATIBLE_VARIABLE_RANGE", critic_codes(card, problem=problem, code_commit=COMMIT))
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
