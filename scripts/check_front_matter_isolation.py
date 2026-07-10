from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.front_matter import split_yaml_front_matter, strip_conversion_front_matter  # noqa: E402
from enh3bench.provenance_rules import contains_mixed_front_matter_and_body  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check conversion front-matter isolation for Markdown files.")
    parser.add_argument("--markdown-dir", type=Path, default=Path("input_markdown"))
    parser.add_argument("--run-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = scan_markdown_dir(args.markdown_dir)
    counts = _counts(rows)
    csv_path = Path("data") / "provenance" / args.run_name / "front_matter_isolation_summary.csv"
    report_path = Path("data") / "reports" / f"front_matter_isolation_report.{args.run_name}.md"
    _write_csv(rows, csv_path)
    _write_report(args.run_name, args.markdown_dir, counts, rows, report_path)
    for key in (
        "total_files",
        "files_with_yaml_front_matter",
        "files_with_repository_cover",
        "files_with_mixed_front_matter_body",
        "files_with_empty_body_after_strip",
    ):
        print(f"{key}: {counts[key]}")
    print(f"csv: {csv_path}")
    print(f"report: {report_path}")
    return 0


def scan_markdown_dir(markdown_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(markdown_dir.glob("*.md")):
        if path.name == ".gitkeep":
            continue
        text = path.read_text(encoding="utf-8")
        yaml_text, _ = split_yaml_front_matter(text)
        isolation = strip_conversion_front_matter(text)
        body_text = str(isolation.get("body_text") or "")
        rows.append(
            {
                "file": str(path),
                "document_id": path.stem,
                "has_yaml_front_matter": yaml_text is not None,
                "has_repository_cover": bool(isolation.get("repository_cover_removed")),
                "has_mixed_front_matter_body": contains_mixed_front_matter_and_body(text),
                "empty_body_after_strip": not bool(body_text.strip()),
                "body_characters": len(body_text),
                "metadata_characters": len(str(isolation.get("metadata_text") or "")),
                "repository_cover_characters": len(str(isolation.get("repository_cover_text") or "")),
                "signals": "; ".join(str(signal) for signal in isolation.get("signals") or []),
            }
        )
    return rows


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_files": len(rows),
        "files_with_yaml_front_matter": sum(1 for row in rows if bool(row["has_yaml_front_matter"])),
        "files_with_repository_cover": sum(1 for row in rows if bool(row["has_repository_cover"])),
        "files_with_mixed_front_matter_body": sum(1 for row in rows if bool(row["has_mixed_front_matter_body"])),
        "files_with_empty_body_after_strip": sum(1 for row in rows if bool(row["empty_body_after_strip"])),
    }


def _write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file",
        "document_id",
        "has_yaml_front_matter",
        "has_repository_cover",
        "has_mixed_front_matter_body",
        "empty_body_after_strip",
        "body_characters",
        "metadata_characters",
        "repository_cover_characters",
        "signals",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    run_name: str,
    markdown_dir: Path,
    counts: dict[str, int],
    rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flagged = [row for row in rows if row["has_yaml_front_matter"] or row["has_repository_cover"] or row["has_mixed_front_matter_body"]]
    lines = [
        f"# Front Matter Isolation Report: {run_name}",
        "",
        f"- Markdown directory: `{markdown_dir}`",
        f"- Total files: {counts['total_files']}",
        f"- Files with YAML front matter: {counts['files_with_yaml_front_matter']}",
        f"- Files with repository cover: {counts['files_with_repository_cover']}",
        f"- Files with mixed front matter/body: {counts['files_with_mixed_front_matter_body']}",
        f"- Files with empty body after strip: {counts['files_with_empty_body_after_strip']}",
        "",
        "## Flagged Files",
        "",
        _table(
            ["Document", "YAML", "Cover", "Mixed", "Empty body", "Body chars", "Signals"],
            [
                [
                    row["document_id"],
                    row["has_yaml_front_matter"],
                    row["has_repository_cover"],
                    row["has_mixed_front_matter_body"],
                    row["empty_body_after_strip"],
                    row["body_characters"],
                    row["signals"],
                ]
                for row in flagged[:50]
            ],
        ),
        "",
        "## Interpretation",
        "",
        (
            "YAML metadata and repository cover pages are low-trust provenance regions. "
            "They are isolated before candidate span extraction so title, abstract, and body text "
            "are not rejected merely because conversion metadata appeared above them."
        ),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "No flagged files."
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
