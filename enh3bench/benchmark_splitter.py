"""Deterministic split helpers for eNH3-BoundaryBench."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any


def deterministic_split(
    records: list[dict[str, Any]],
    train_frac: float = 0.7,
    dev_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 13,
    group_key: str = "paper_id",
) -> dict[str, list[dict[str, Any]]]:
    """Split records by group with a deterministic seed."""

    if not records:
        return {"train": [], "dev": [], "test": []}
    groups: dict[str, list[dict[str, Any]]] = {}
    group_order: list[str] = []
    for record in records:
        key = _group_value(record, group_key)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(record)

    shuffled = list(group_order)
    random.Random(seed).shuffle(shuffled)
    train_groups, dev_groups, test_groups = _assign_groups(shuffled, train_frac, dev_frac, test_frac)
    assignments = {group: "train" for group in train_groups}
    assignments.update({group: "dev" for group in dev_groups})
    assignments.update({group: "test" for group in test_groups})

    splits = {"train": [], "dev": [], "test": []}
    for record in records:
        split = assignments[_group_value(record, group_key)]
        splits[split].append(record)
    return splits


def split_tasks_by_group(
    tasks: dict[str, list[dict[str, Any]]],
    seed: int = 13,
    group_key: str = "paper_id",
    train_frac: float = 0.7,
    dev_frac: float = 0.15,
    test_frac: float = 0.15,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Split each task by group."""

    return {
        task_name: deterministic_split(
            records,
            train_frac=train_frac,
            dev_frac=dev_frac,
            test_frac=test_frac,
            seed=seed,
            group_key=group_key,
        )
        for task_name, records in tasks.items()
    }


def export_splits(
    split_tasks: dict[str, dict[str, list[dict[str, Any]]]],
    run_name: str,
    output_dir: str | Path = "data/benchmarks",
) -> dict[str, Any]:
    """Export train/dev/test task splits and a manifest."""

    split_dir = Path(output_dir) / run_name / "splits"
    outputs: dict[str, Any] = {}
    warnings: list[str] = []
    for task_name, splits in split_tasks.items():
        task_outputs: dict[str, Any] = {}
        group_sets: dict[str, set[str]] = {}
        for split_name in ("train", "dev", "test"):
            records = splits.get(split_name, [])
            jsonl_path = split_dir / f"{task_name}.{split_name}.jsonl"
            csv_path = split_dir / f"{task_name}.{split_name}.csv"
            _write_jsonl(records, jsonl_path)
            _write_csv(records, csv_path)
            task_outputs[split_name] = {"count": len(records), "jsonl": str(jsonl_path), "csv": str(csv_path)}
            group_sets[split_name] = {_group_value(record, "paper_id") for record in records}
            if not records:
                warnings.append(f"{task_name}.{split_name} is empty; dataset may be too small for all splits.")
        if group_sets["train"] & group_sets["dev"] or group_sets["train"] & group_sets["test"] or group_sets["dev"] & group_sets["test"]:
            warnings.append(f"{task_name} has overlapping groups across splits.")
        outputs[task_name] = task_outputs

    manifest = {
        "run_name": run_name,
        "splits": outputs,
        "warnings": sorted(set(warnings)),
    }
    manifest_path = split_dir / "split_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return {"run_name": run_name, "manifest": str(manifest_path), "splits": outputs, "warnings": manifest["warnings"]}


def _assign_groups(
    groups: list[str],
    train_frac: float,
    dev_frac: float,
    test_frac: float,
) -> tuple[set[str], set[str], set[str]]:
    total = len(groups)
    if total == 1:
        return {groups[0]}, set(), set()
    if total == 2:
        return {groups[0]}, set(), {groups[1]}

    total_frac = train_frac + dev_frac + test_frac
    if total_frac <= 0:
        train_frac, dev_frac, test_frac = 0.7, 0.15, 0.15
        total_frac = 1.0
    train_target = train_frac / total_frac
    dev_target = dev_frac / total_frac
    train_count = max(1, int(round(total * train_target)))
    dev_count = int(round(total * dev_target))
    if train_count + dev_count >= total:
        dev_count = max(0, total - train_count - 1)
    test_count = total - train_count - dev_count
    if test_count < 0:
        test_count = 0
    train = set(groups[:train_count])
    dev = set(groups[train_count : train_count + dev_count])
    test = set(groups[train_count + dev_count :])
    return train, dev, test


def _group_value(record: dict[str, Any], group_key: str) -> str:
    for key in (group_key, "paper_id", "document_id", "source_span_id", "evidence_id", "benchmark_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return "missing_group"


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(records)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for record in records:
        for key in record:
            if key not in names:
                names.append(key)
    return names or ["benchmark_id"]


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
