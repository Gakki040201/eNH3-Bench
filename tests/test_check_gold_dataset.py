from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_gold_dataset import check_gold_dataset  # noqa: E402


class CheckGoldDatasetTests(unittest.TestCase):
    def test_valid_template_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_dataset(Path(temp_dir), source_span="")
            result = check_gold_dataset(
                paths["papers"],
                paths["spans"],
                paths["gold"],
                allow_empty_source_span=True,
                report_path=paths["report"],
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["summary"]["paper_count"], 1)
            self.assertTrue(paths["report"].exists())

    def test_missing_paper_id_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_dataset(Path(temp_dir), span_paper_id="P999", source_span="")
            result = check_gold_dataset(
                paths["papers"],
                paths["spans"],
                paths["gold"],
                allow_empty_source_span=True,
                report_path=paths["report"],
            )
            self.assertFalse(result["ok"])
            self.assertTrue(any("references missing paper_id P999" in error for error in result["errors"]))

    def test_empty_source_span_fails_in_final_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_dataset(Path(temp_dir), source_span="")
            result = check_gold_dataset(
                paths["papers"],
                paths["spans"],
                paths["gold"],
                allow_empty_source_span=False,
                report_path=paths["report"],
            )
            self.assertFalse(result["ok"])
            self.assertTrue(any("source_span" in error for error in result["errors"]))

    def test_summary_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_dataset(
                Path(temp_dir),
                source_span="A compact source span with explicit support.",
                reaction_family="LiNRR",
                reliability_label="B",
                evidence_type="primary_claim",
            )
            result = check_gold_dataset(
                paths["papers"],
                paths["spans"],
                paths["gold"],
                allow_empty_source_span=False,
                report_path=paths["report"],
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["summary"]["reaction_family"]["LiNRR"], 1)
            self.assertEqual(result["summary"]["reliability_label"]["B"], 1)
            self.assertEqual(result["summary"]["evidence_type"]["primary_claim"], 1)


def _write_dataset(
    directory: Path,
    span_paper_id: str = "P001",
    gold_paper_id: str = "P001",
    source_span: str = "A compact source span with explicit support.",
    reaction_family: str = "eNRR",
    reliability_label: str = "C",
    evidence_type: str = "primary_claim",
) -> dict[str, Path]:
    papers = directory / "papers.csv"
    spans = directory / "spans.jsonl"
    gold = directory / "gold.jsonl"
    report = directory / "report.md"

    papers.write_text(
        "paper_id,title,doi,year,journal,article_type,reaction_family_slot,"
        "purpose_in_benchmark,expected_difficult_fields,notes\n"
        "P001,,,,,primary_research,eNRR,unit test slot,source_span,unit test\n",
        encoding="utf-8",
    )
    spans.write_text(
        json.dumps(
            {
                "span_id": "S001_1",
                "paper_id": span_paper_id,
                "source_section": "results",
                "text": source_span,
                "annotation_status": "todo",
                "notes": "test span",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    gold.write_text(
        json.dumps(
            {
                "evidence_id": "E001_1",
                "paper_id": gold_paper_id,
                "source_span": source_span,
                "source_section": "results",
                "reaction_family": reaction_family,
                "nitrogen_source": "N2",
                "catalyst": None,
                "catalyst_class": None,
                "electrolyte": None,
                "reactor_type": None,
                "membrane": None,
                "potential_value": None,
                "potential_unit": None,
                "potential_reference": None,
                "current_density_mA_cm2": None,
                "faradaic_efficiency_percent": None,
                "nh3_yield_value": None,
                "nh3_yield_unit": None,
                "nh3_yield_normalized_value": None,
                "nh3_yield_normalized_unit": None,
                "energy_efficiency_percent": None,
                "stability_hours": None,
                "detection_method": None,
                "isotope_validation": "unclear",
                "blank_control": "unclear",
                "contamination_control": "unclear",
                "nox_screening": "unclear",
                "reliability_label": reliability_label,
                "evidence_type": evidence_type,
                "gold_notes": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return {"papers": papers, "spans": spans, "gold": gold, "report": report}


if __name__ == "__main__":
    unittest.main()
