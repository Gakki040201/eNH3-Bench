from __future__ import annotations

import argparse
import sys
from pathlib import Path


REQUIRED_COLUMNS = [
    "date",
    "external_repo",
    "license",
    "external_file_or_component",
    "local_file",
    "copied_code",
    "adaptation_type",
    "attribution_action",
    "notes",
]


def parse_reuse_log(path: Path) -> list[dict[str, str]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    if len(table_lines) < 2:
        raise ValueError("No Markdown table found")
    headers = _split_row(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _split_row(line)
        if len(cells) != len(headers):
            raise ValueError(f"Row has {len(cells)} cells but expected {len(headers)}: {line}")
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def validate_reuse_log(path: Path) -> list[str]:
    rows = parse_reuse_log(path)
    errors: list[str] = []
    headers = list(rows[0].keys()) if rows else _split_row(_table_header(path))
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
    for index, row in enumerate(rows, start=1):
        copied_code = row.get("copied_code", "").strip().casefold()
        if copied_code == "yes":
            if not row.get("attribution_action", "").strip():
                errors.append(f"row {index}: attribution_action is required when copied_code=yes")
            local_file = row.get("local_file", "").strip().casefold()
            if not local_file or local_file == "pending":
                errors.append(f"row {index}: local_file must be set when copied_code=yes")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate external code reuse log.")
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("docs") / "code_reuse_log.md",
        help="Path to code reuse log Markdown file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_reuse_log(args.log)
    rows = parse_reuse_log(args.log)
    copied = sum(1 for row in rows if row.get("copied_code", "").strip().casefold() == "yes")
    print(f"Checked {len(rows)} reuse log rows; copied_code=yes rows: {copied}")
    if errors:
        print("Reuse log check failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Reuse log check passed")
    return 0


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_header(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and line.endswith("|"):
            return line
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
