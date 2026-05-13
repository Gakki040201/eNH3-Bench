"""Storage helpers for eNH3-ExtractBench method runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_BASE_DIR = Path("data") / "extraction_runs"


def write_method_records(
    records: list[dict[str, Any]],
    run_name: str,
    method_name: str,
    base_dir: str | Path = DEFAULT_BASE_DIR,
) -> Path:
    """Write method records to data/extraction_runs/{run_name}/{method_name}.jsonl."""

    path = Path(base_dir) / run_name / f"{method_name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
    return path


def load_method_records(
    run_name: str,
    method_name: str,
    base_dir: str | Path = DEFAULT_BASE_DIR,
) -> list[dict[str, Any]]:
    """Load method records from a stored run."""

    path = Path(base_dir) / run_name / f"{method_name}.jsonl"
    return load_jsonl(path)


def list_run_methods(run_name: str, base_dir: str | Path = DEFAULT_BASE_DIR) -> list[str]:
    """Return method names present in a run directory."""

    run_dir = Path(base_dir) / run_name
    if not run_dir.exists():
        return []
    return sorted(path.stem for path in run_dir.glob("*.jsonl") if path.is_file())


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dictionaries."""

    records: list[dict[str, Any]] = []
    input_path = Path(path)
    if not input_path.exists():
        return records
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
