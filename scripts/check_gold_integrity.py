from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.audit_schema import HUMAN_FIELDS, normalize_list_field  # noqa: E402


MANIFEST_SCHEMA_VERSION = "1.0"
EXPECTED_GOLD_RECORDS = 100
DEFAULT_BASELINE_PATH = ROOT / "config" / "gold_integrity_baselines.json"
DISTRIBUTION_FIELDS = (
    "human_review_status",
    "human_text_class",
    "human_maximum_supported_boundary",
    "human_admissibility_status",
    "human_experiment_decision",
)
LIST_LABEL_FIELDS = {"human_required_controls", "human_hidden_tax"}


def check_gold_integrity(
    jsonl_path: str | Path,
    csv_path: str | Path,
    *,
    run_name: str,
    baseline_path: str | Path | None = None,
    require_baseline: bool = False,
    allow_additive_schema_fields: bool = False,
    output_path: str | Path | None = None,
    expected_records: int = EXPECTED_GOLD_RECORDS,
) -> dict[str, Any]:
    """Check paired human Gold exports and optionally enforce an exact-byte baseline."""

    jsonl_path = Path(jsonl_path)
    csv_path = Path(csv_path)
    errors: list[str] = []
    jsonl_records = _load_jsonl(jsonl_path, errors)
    csv_records = _load_csv(csv_path, errors)
    jsonl_summary = _summarize(jsonl_path, jsonl_records)
    csv_summary = _summarize(csv_path, csv_records)

    resolved_baseline = Path(baseline_path) if baseline_path is not None else DEFAULT_BASELINE_PATH
    baseline_config, baseline_load_errors = _load_baseline_config(resolved_baseline)
    run_baseline = _run_baseline(baseline_config, run_name)
    baseline_found = run_baseline is not None
    expected, baseline_value_errors = _expected_values(run_baseline, expected_records)
    baseline_complete = not baseline_value_errors and baseline_found
    exact_hash_enforced = baseline_complete and not allow_additive_schema_fields

    explicit_baseline = baseline_path is not None
    if (require_baseline or explicit_baseline) and baseline_load_errors:
        errors.extend(baseline_load_errors)
    if (require_baseline or explicit_baseline) and not baseline_found:
        errors.append(f"required baseline not found for run: {run_name}")
    elif baseline_found and baseline_value_errors:
        errors.extend(baseline_value_errors)

    jsonl_count_match = jsonl_summary["records"] == expected["jsonl_record_count"]
    csv_count_match = csv_summary["records"] == expected["csv_record_count"]
    jsonl_hash_match = _hash_match(jsonl_summary["sha256"], expected["jsonl_sha256"])
    csv_hash_match = _hash_match(csv_summary["sha256"], expected["csv_sha256"])
    source_span_ids_match = jsonl_summary["source_span_ids"] == csv_summary["source_span_ids"]
    label_mismatches = _label_mismatches(jsonl_records, csv_records)
    human_labels_match = source_span_ids_match and not label_mismatches

    _check_unique_ids("JSONL", jsonl_records, errors)
    _check_unique_ids("CSV", csv_records, errors)
    if not jsonl_count_match:
        errors.append(
            f"JSONL record count changed: expected {expected['jsonl_record_count']}, found {jsonl_summary['records']}"
        )
    if not csv_count_match:
        errors.append(f"CSV record count changed: expected {expected['csv_record_count']}, found {csv_summary['records']}")
    if not source_span_ids_match:
        jsonl_ids = set(jsonl_summary["source_span_ids"])
        csv_ids = set(csv_summary["source_span_ids"])
        errors.append(
            "JSONL/CSV source_span_id sets differ: "
            f"JSONL-only={sorted(jsonl_ids - csv_ids)}, CSV-only={sorted(csv_ids - jsonl_ids)}"
        )
    errors.extend(label_mismatches)
    if exact_hash_enforced and not jsonl_hash_match:
        errors.append(
            f"JSONL SHA-256 changed: expected {expected['jsonl_sha256']}, found {jsonl_summary['sha256']}"
        )
    if exact_hash_enforced and not csv_hash_match:
        errors.append(f"CSV SHA-256 changed: expected {expected['csv_sha256']}, found {csv_summary['sha256']}")

    checks = {
        "jsonl_hash_match": jsonl_hash_match,
        "csv_hash_match": csv_hash_match,
        "jsonl_count_match": jsonl_count_match,
        "csv_count_match": csv_count_match,
        "source_span_ids_match": source_span_ids_match,
        "human_labels_match": human_labels_match,
    }
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "run_name": run_name,
        "baseline_required": bool(require_baseline),
        "baseline_found": baseline_found,
        "baseline_source": str(resolved_baseline),
        "exact_hash_enforced": exact_hash_enforced,
        "allow_additive_schema_fields": bool(allow_additive_schema_fields),
        "expected": expected,
        "actual": {
            "jsonl_record_count": jsonl_summary["records"],
            "jsonl_sha256": jsonl_summary["sha256"],
            "csv_record_count": csv_summary["records"],
            "csv_sha256": csv_summary["sha256"],
        },
        "checks": checks,
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "details": {"jsonl": jsonl_summary, "csv": csv_summary},
    }
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


def _load_baseline_config(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, [f"baseline config not found: {path}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, [f"invalid baseline config {path}: {exc}"]
    if not isinstance(value, dict):
        return None, [f"baseline config is not an object: {path}"]
    return value, []


def _run_baseline(config: dict[str, Any] | None, run_name: str) -> dict[str, Any] | None:
    if not config or not isinstance(config.get("runs"), dict):
        return None
    value = config["runs"].get(run_name)
    return value if isinstance(value, dict) else None


def _expected_values(run_baseline: dict[str, Any] | None, fallback_count: int) -> tuple[dict[str, Any], list[str]]:
    expected = {
        "jsonl_record_count": int(fallback_count),
        "jsonl_sha256": None,
        "csv_record_count": int(fallback_count),
        "csv_sha256": None,
    }
    if run_baseline is None:
        return expected, []

    errors: list[str] = []
    for label in ("jsonl", "csv"):
        config = run_baseline.get(label)
        if not isinstance(config, dict):
            errors.append(f"baseline missing {label} configuration")
            continue
        count = config.get("record_count")
        sha256 = str(config.get("sha256") or "").strip().upper()
        if count is None:
            errors.append(f"baseline missing {label} record_count")
        else:
            try:
                expected[f"{label}_record_count"] = int(count)
            except (TypeError, ValueError):
                errors.append(f"baseline has invalid {label} record_count: {count}")
        if not sha256:
            errors.append(f"baseline missing {label} sha256")
        elif len(sha256) != 64 or any(character not in "0123456789ABCDEF" for character in sha256):
            errors.append(f"baseline has invalid {label} sha256: {sha256}")
        else:
            expected[f"{label}_sha256"] = sha256
    return expected, errors


def _load_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        errors.append(f"missing Gold JSONL: {path}")
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSONL at line {line_number}: {exc.msg}")
                continue
            if isinstance(value, dict):
                records.append(value)
            else:
                errors.append(f"JSONL line {line_number} is not an object")
    return records


def _load_csv(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        errors.append(f"missing Gold CSV: {path}")
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except csv.Error as exc:
        errors.append(f"invalid Gold CSV: {exc}")
        return []


def _summarize(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "records": len(records),
        "sha256": _sha256(path) if path.exists() else None,
        "source_span_ids": sorted(_field_set(records, "source_span_id")),
        "paper_ids": sorted(_field_set(records, "paper_id")),
        "distributions": {field: _distribution(records, field) for field in DISTRIBUTION_FIELDS},
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _hash_match(actual: str | None, expected: str | None) -> bool | None:
    if expected is None:
        return None
    return actual == expected


def _field_set(records: list[dict[str, Any]], field: str) -> set[str]:
    return {str(record.get(field) or "").strip() for record in records if str(record.get(field) or "").strip()}


def _distribution(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(record.get(field) or "<missing>").strip() or "<missing>" for record in records)
    return dict(sorted(counts.items()))


def _check_unique_ids(label: str, records: list[dict[str, Any]], errors: list[str]) -> None:
    ids = [str(record.get("source_span_id") or "").strip() for record in records]
    if any(not value for value in ids):
        errors.append(f"{label} contains an empty source_span_id")
    duplicates = sorted(value for value, count in Counter(ids).items() if value and count > 1)
    if duplicates:
        errors.append(f"{label} contains duplicate source_span_id values: {duplicates}")


def _label_mismatches(jsonl_records: list[dict[str, Any]], csv_records: list[dict[str, Any]]) -> list[str]:
    left = _record_index(jsonl_records)
    right = _record_index(csv_records)
    errors: list[str] = []
    for source_span_id in sorted(set(left) & set(right)):
        if left[source_span_id] != right[source_span_id]:
            changed = sorted(key for key in left[source_span_id] if left[source_span_id].get(key) != right[source_span_id].get(key))
            errors.append(f"JSONL/CSV labels differ for {source_span_id}: {changed}")
    return errors


def _record_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        source_span_id = str(record.get("source_span_id") or "").strip()
        if not source_span_id:
            continue
        labels = {field: _normalize_label(field, record.get(field)) for field in HUMAN_FIELDS}
        index[source_span_id] = {"paper_id": str(record.get("paper_id") or "").strip(), **labels}
    return dict(sorted(index.items()))


def _normalize_label(field: str, value: Any) -> Any:
    if field in LIST_LABEL_FIELDS:
        return sorted(normalize_list_field(value))
    return str(value or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check human Gold integrity.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--baseline-json", type=Path)
    parser.add_argument("--require-baseline", action="store_true")
    parser.add_argument("--allow-additive-schema-fields", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gold_dir = ROOT / "data" / "gold" / args.run_name
    result = check_gold_integrity(
        gold_dir / "human_gold_claim_rights.jsonl",
        gold_dir / "human_gold_claim_rights.csv",
        run_name=args.run_name,
        baseline_path=args.baseline_json,
        require_baseline=args.require_baseline,
        allow_additive_schema_fields=args.allow_additive_schema_fields,
        output_path=args.output,
    )
    print(f"gold_integrity: {result['result']}")
    print(f"baseline_required: {result['baseline_required']}")
    print(f"baseline_found: {result['baseline_found']}")
    print(f"exact_hash_enforced: {result['exact_hash_enforced']}")
    print(f"jsonl_records: {result['actual']['jsonl_record_count']}")
    print(f"jsonl_sha256: {result['actual']['jsonl_sha256']}")
    print(f"csv_records: {result['actual']['csv_record_count']}")
    print(f"csv_sha256: {result['actual']['csv_sha256']}")
    print(f"manifest: {args.output}")
    for error in result["errors"]:
        print(f"- {error}")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
