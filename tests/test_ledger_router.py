from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.ledger_router import classify_and_route_spans


class LedgerRouterTests(unittest.TestCase):
    def test_classify_and_route_writes_all_ledgers(self) -> None:
        spans = [
            {
                "span_id": "S001",
                "paper_id": "P001",
                "text": "N2 reduction produced NH3 at 10.5 nmol s-1 cm-2 with 62% FE and 15N2 isotope labeling.",
            },
            {"span_id": "S002", "paper_id": "P002", "text": "Table S1 review table of previous reports."},
            {"span_id": "S003", "paper_id": "P003", "text": "Nitrate contamination was detected."},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            classified, manifest = classify_and_route_spans(spans, "test", Path(temp_dir))
            run_dir = Path(temp_dir) / "test"

            self.assertEqual(len(classified), 3)
            self.assertTrue((run_dir / "classified_spans.jsonl").exists())
            self.assertTrue((run_dir / "performance_ledger.jsonl").exists())
            self.assertTrue((run_dir / "secondary_review_ledger.csv").exists())
            self.assertEqual(manifest["ledger_counts"]["performance_ledger"], 1)
            self.assertEqual(manifest["ledger_counts"]["negative_evidence_ledger"], 1)

            performance = [
                json.loads(line)
                for line in (run_dir / "performance_ledger.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(performance[0]["span_id"], "S001")

            with (run_dir / "classified_spans.csv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["paper_id"], "P001")


if __name__ == "__main__":
    unittest.main()
