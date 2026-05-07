from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.schema import EvidenceRecord, evidence_to_dict  # noqa: E402


DEFAULT_INPUT = ROOT / "data" / "spans" / "spans.example.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "gold" / "gold.template.jsonl"


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc


def evidence_id_from_span(span: dict[str, Any]) -> str:
    span_id = str(span.get("span_id", "")).strip()
    if span_id.startswith("S") and len(span_id) > 1:
        return f"E{span_id[1:]}"
    if span_id:
        return f"E_{span_id}"
    return "E_TODO"


def template_from_span(span: dict[str, Any]) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id_from_span(span),
        paper_id=str(span.get("paper_id", "")).strip(),
        source_span=str(span.get("text", "")).strip(),
        source_section=str(span.get("source_section", "unknown")).strip() or "unknown",
        reaction_family="unclear",
        nitrogen_source="unknown",
        catalyst=None,
        catalyst_class=None,
        electrolyte=None,
        reactor_type=None,
        membrane=None,
        potential_value=None,
        potential_unit=None,
        potential_reference=None,
        current_density_mA_cm2=None,
        faradaic_efficiency_percent=None,
        nh3_yield_value=None,
        nh3_yield_unit=None,
        nh3_yield_normalized_value=None,
        nh3_yield_normalized_unit=None,
        energy_efficiency_percent=None,
        stability_hours=None,
        detection_method=None,
        isotope_validation="unclear",
        blank_control="unclear",
        contamination_control="unclear",
        nox_screening="unclear",
        reliability_label="D",
        evidence_type="primary_claim",
        gold_notes=None,
    )


def write_templates(input_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for span in iter_jsonl(input_path):
            record = template_from_span(span)
            handle.write(json.dumps(evidence_to_dict(record), separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create empty gold templates from span JSONL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input span JSONL file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output gold JSONL file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    count = write_templates(args.input, args.output)
    print(f"Wrote {count} template records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
