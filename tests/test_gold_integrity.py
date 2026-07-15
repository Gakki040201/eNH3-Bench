from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_gold_integrity import DEFAULT_BASELINE_PATH, check_gold_integrity


ROOT = Path(__file__).resolve().parents[1]


class GoldIntegrityTests(unittest.TestCase):
    def test_exact_baseline_passes_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1"), _record("S2", paper_id="P2")])
            baseline = _write_baseline(base, "fixture", jsonl_path, csv_path)
            output = base / "manifest.json"
            result = check_gold_integrity(
                jsonl_path,
                csv_path,
                run_name="fixture",
                baseline_path=baseline,
                require_baseline=True,
                output_path=output,
            )
            self.assertEqual(result["result"], "PASS")
            self.assertTrue(result["baseline_required"])
            self.assertTrue(result["baseline_found"])
            self.assertTrue(result["exact_hash_enforced"])
            self.assertTrue(result["checks"]["jsonl_hash_match"])
            self.assertTrue(result["checks"]["csv_hash_match"])
            self.assertTrue(output.exists())

    def test_human_field_change_fails_exact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1")])
            baseline = _write_baseline(base, "fixture", jsonl_path, csv_path)
            changed = _record("S1")
            changed["human_experiment_decision"] = "needs_second_reviewer"
            _write_pair(base, [changed])
            result = _check_fixture(jsonl_path, csv_path, baseline)
            self.assertEqual(result["result"], "FAIL")
            self.assertFalse(result["checks"]["jsonl_hash_match"])
            self.assertFalse(result["checks"]["csv_hash_match"])

    def test_non_human_field_change_fails_exact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1")])
            baseline = _write_baseline(base, "fixture", jsonl_path, csv_path)
            changed = _record("S1")
            changed["machine_note"] = "non-human field changed"
            _write_pair(base, [changed])
            result = _check_fixture(jsonl_path, csv_path, baseline)
            self.assertEqual(result["result"], "FAIL")
            self.assertTrue(result["checks"]["human_labels_match"])
            self.assertFalse(result["checks"]["jsonl_hash_match"])

    def test_jsonl_row_order_change_fails_exact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            records = [_record("S1"), _record("S2")]
            jsonl_path, csv_path = _write_pair(base, records)
            baseline = _write_baseline(base, "fixture", jsonl_path, csv_path)
            _write_jsonl(jsonl_path, list(reversed(records)))
            result = _check_fixture(jsonl_path, csv_path, baseline)
            self.assertEqual(result["result"], "FAIL")
            self.assertTrue(result["checks"]["source_span_ids_match"])
            self.assertTrue(result["checks"]["human_labels_match"])
            self.assertFalse(result["checks"]["jsonl_hash_match"])

    def test_csv_column_order_change_fails_exact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            records = [_record("S1")]
            jsonl_path, csv_path = _write_pair(base, records)
            baseline = _write_baseline(base, "fixture", jsonl_path, csv_path)
            _write_csv(csv_path, records, fieldnames=list(reversed(records[0].keys())))
            result = _check_fixture(jsonl_path, csv_path, baseline)
            self.assertEqual(result["result"], "FAIL")
            self.assertTrue(result["checks"]["human_labels_match"])
            self.assertFalse(result["checks"]["csv_hash_match"])

    def test_require_baseline_missing_run_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1")])
            baseline = base / "baseline.json"
            baseline.write_text(json.dumps({"schema_version": "1.0", "runs": {}}), encoding="utf-8")
            result = check_gold_integrity(
                jsonl_path,
                csv_path,
                run_name="missing",
                baseline_path=baseline,
                require_baseline=True,
                expected_records=1,
            )
            self.assertEqual(result["result"], "FAIL")
            self.assertFalse(result["baseline_found"])

    def test_required_baseline_missing_sha_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1")])
            baseline = _write_baseline(base, "fixture", jsonl_path, csv_path, omit_csv_hash=True)
            result = _check_fixture(jsonl_path, csv_path, baseline)
            self.assertEqual(result["result"], "FAIL")
            self.assertFalse(result["exact_hash_enforced"])
            self.assertTrue(any("missing csv sha256" in error for error in result["errors"]))

    def test_generic_check_without_matching_baseline_is_not_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1")])
            result = check_gold_integrity(
                jsonl_path,
                csv_path,
                run_name="fixture_not_in_default_config",
                expected_records=1,
            )
            self.assertEqual(result["result"], "PASS")
            self.assertFalse(result["baseline_found"])
            self.assertFalse(result["exact_hash_enforced"])

    def test_jsonl_csv_id_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            jsonl_path, csv_path = _write_pair(base, [_record("S1")])
            _write_csv(csv_path, [_record("S2")])
            result = check_gold_integrity(
                jsonl_path,
                csv_path,
                run_name="fixture_not_in_default_config",
                expected_records=1,
            )
            self.assertEqual(result["result"], "FAIL")
            self.assertFalse(result["checks"]["source_span_ids_match"])

    def test_authoritative_gold_matches_versioned_exact_baseline(self) -> None:
        run_name = "enrr_round1_oa_20260712"
        gold_dir = ROOT / "data" / "gold" / run_name
        jsonl_path = gold_dir / "human_gold_claim_rights.jsonl"
        csv_path = gold_dir / "human_gold_claim_rights.csv"
        if not jsonl_path.exists() or not csv_path.exists():
            self.skipTest("authoritative Gold files are not distributed in the Git checkout")
        result = check_gold_integrity(
            jsonl_path,
            csv_path,
            run_name=run_name,
            baseline_path=DEFAULT_BASELINE_PATH,
            require_baseline=True,
        )
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["actual"]["jsonl_record_count"], 100)
        self.assertEqual(result["actual"]["csv_record_count"], 100)
        self.assertTrue(result["checks"]["jsonl_hash_match"])
        self.assertTrue(result["checks"]["csv_hash_match"])


def _check_fixture(jsonl_path: Path, csv_path: Path, baseline: Path) -> dict[str, object]:
    return check_gold_integrity(
        jsonl_path,
        csv_path,
        run_name="fixture",
        baseline_path=baseline,
        require_baseline=True,
        expected_records=1,
    )


def _record(source_span_id: str, paper_id: str = "P1") -> dict[str, object]:
    return {
        "source_span_id": source_span_id,
        "paper_id": paper_id,
        "machine_note": "unchanged",
        "human_reviewer_id": "reviewer",
        "human_review_status": "reviewed",
        "human_text_class": "reference_list",
        "human_maximum_supported_boundary": "unsupported_or_secondary",
        "human_admissibility_status": "reject_or_low_trust_provenance",
        "human_required_controls": ["primary body text pairing"],
        "human_hidden_tax": [],
        "human_experiment_decision": "discard_as_secondary",
        "human_validation_isotope_15N": "secondary_only",
        "human_validation_blank_control": "secondary_only",
        "human_validation_NOx_control": "secondary_only",
        "human_validation_contamination_control": "secondary_only",
        "human_validation_quantification_method": "secondary_only",
        "human_notes": "fixture",
    }


def _write_pair(base: Path, records: list[dict[str, object]]) -> tuple[Path, Path]:
    jsonl_path = base / "gold.jsonl"
    csv_path = base / "gold.csv"
    _write_jsonl(jsonl_path, records)
    _write_csv(csv_path, records)
    return jsonl_path, csv_path


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def _write_csv(path: Path, records: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    names = fieldnames or (list(records[0]) if records else ["source_span_id", "paper_id"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {key: json.dumps(record.get(key)) if isinstance(record.get(key), (list, dict)) else record.get(key) for key in names}
            )


def _write_baseline(
    base: Path,
    run_name: str,
    jsonl_path: Path,
    csv_path: Path,
    *,
    omit_csv_hash: bool = False,
) -> Path:
    csv_config: dict[str, object] = {}
    if not omit_csv_hash:
        csv_config["sha256"] = _hash(csv_path)
    config = {
        "schema_version": "1.0",
        "runs": {
            run_name: {
                "jsonl": {"record_count": _record_count(jsonl_path), "sha256": _hash(jsonl_path)},
                "csv": {"record_count": _csv_record_count(csv_path), **csv_config},
            }
        },
    }
    path = base / "baseline.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _record_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _csv_record_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
