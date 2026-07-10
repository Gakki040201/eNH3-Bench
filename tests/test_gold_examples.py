from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.schema import (  # noqa: E402
    SOURCE_SECTIONS,
    evidence_from_dict,
    paper_from_dict,
    validate_evidence_record,
    validate_paper_record,
)


PAPERS_PATH = ROOT / "data" / "papers" / "papers.example.csv"
SPANS_PATH = ROOT / "data" / "spans" / "spans.example.jsonl"
GOLD_PATH = ROOT / "data" / "gold" / "gold.example.jsonl"


def parse_optional_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def parse_optional_bool(value: str) -> bool | None:
    value = value.strip().lower()
    if value == "":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def empty_to_none(value: str) -> str | None:
    value = value.strip()
    return value or None


def load_papers() -> list[dict[str, Any]]:
    with PAPERS_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["year"] = parse_optional_int(row["year"])
        row["open_access"] = parse_optional_bool(row["open_access"])
        row["source_file"] = empty_to_none(row["source_file"])
        row["doi"] = empty_to_none(row["doi"])
        row["journal"] = empty_to_none(row["journal"])
        row["notes"] = empty_to_none(row["notes"])
    return rows


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AssertionError(f"Invalid JSON on line {line_number} of {path}") from exc
    return records


class GoldExampleTests(unittest.TestCase):
    def test_example_papers_validate(self) -> None:
        papers = [paper_from_dict(row) for row in load_papers()]
        self.assertEqual(len(papers), 3)
        for paper in papers:
            self.assertEqual(validate_paper_record(paper), [])

    def test_example_spans_are_well_formed(self) -> None:
        spans = load_jsonl(SPANS_PATH)
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertTrue(span["span_id"].strip())
            self.assertTrue(span["paper_id"].strip())
            self.assertIn(span["source_section"], SOURCE_SECTIONS)
            self.assertTrue(span["text"].strip())

    @unittest.skipUnless(GOLD_PATH.exists(), "sample gold file is optional after data cleanup")
    def test_example_gold_records_validate(self) -> None:
        gold = [evidence_from_dict(row) for row in load_jsonl(GOLD_PATH)]
        self.assertEqual(len(gold), 3)
        for record in gold:
            self.assertEqual(validate_evidence_record(record), [])

    @unittest.skipUnless(GOLD_PATH.exists(), "sample gold file is optional after data cleanup")
    def test_gold_records_are_grounded_in_spans(self) -> None:
        span_text = {span["text"] for span in load_jsonl(SPANS_PATH)}
        for record in [evidence_from_dict(row) for row in load_jsonl(GOLD_PATH)]:
            self.assertIn(record.source_span, span_text)

    @unittest.skipUnless(GOLD_PATH.exists(), "sample gold file is optional after data cleanup")
    def test_lianrr_and_no3rr_examples_exist(self) -> None:
        families = {row["reaction_family"] for row in load_jsonl(GOLD_PATH)}
        self.assertIn("LiNRR", families)
        self.assertIn("NO3RR", families)


if __name__ == "__main__":
    unittest.main()
