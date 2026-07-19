from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.context_packet import build_context_packets, export_context_packets


class ContextPacketSerializationTests(unittest.TestCase):
    def test_jsonl_csv_summary_and_report_are_written_with_stable_json_cells(self) -> None:
        evidence = [{"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "Background context.", "text_class": "background_context", "provenance_type": "body"}]
        packets = build_context_packets(evidence, [], [], [], run_name="fixture")
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            outputs = export_context_packets(packets, "fixture", output_dir=base / "packets", report_dir=base / "reports")
            self.assertTrue(Path(outputs["jsonl"]).exists())
            self.assertTrue(Path(outputs["summary"]).exists())
            self.assertTrue(Path(outputs["report"]).exists())
            with Path(outputs["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertIsInstance(json.loads(row["previous_spans"]), list)
            self.assertIsInstance(json.loads(row["context_missing_types"]), list)
            summary = json.loads(Path(outputs["summary"]).read_text(encoding="utf-8"))
            self.assertEqual(summary["packet_count"], 1)


if __name__ == "__main__":
    unittest.main()
