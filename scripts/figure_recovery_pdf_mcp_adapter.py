"""Isolated local adapter for pdf-mcp's vector chart extractor.

This adapter never performs network access. It deliberately returns the
extractor's verification state and point count without granting scientific
authority to the result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sys.path.insert(0, str(args.repo / "src"))
    import fitz
    from pdf_mcp import chart_extractor

    version = "unknown"
    pyproject = args.repo / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.startswith("version = "):
                version = line.split("=", 1)[1].strip().strip('"')
                break
    with fitz.open(args.pdf) as document:
        result = chart_extractor.extract_charts(document, args.page - 1, max_points=24)
    charts = result.get("charts") or []
    point_count = sum(len(curve.get("points") or []) for chart in charts for curve in chart.get("curves") or [])
    status = str(result.get("status") or "declined")
    payload = {
        "extractor": "pdf-mcp/pdf_extract_chart", "version": version,
        "repo_commit": _commit(args.repo), "result": status,
        "decline_reason": "; ".join(str(item) for item in result.get("reasons") or []) or None,
        "questions": result.get("questions") or [], "point_count": point_count,
        "chart_count": len(charts), "raw_result": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    return 0


def _commit(repo: Path) -> str | None:
    import subprocess
    completed = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


if __name__ == "__main__":
    raise SystemExit(main())
