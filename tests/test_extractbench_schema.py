from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.extractbench_schema import (  # noqa: E402
    ExtractBenchRecord,
    record_from_dict,
    record_to_dict,
    validate_extractbench_record,
)


def make_record() -> ExtractBenchRecord:
    return ExtractBenchRecord(
        record_id="E001",
        paper_id="P001",
        source_span="Li-mediated NRR gave FE 61% with 15N validation.",
        method_name="test_method",
        reaction_family="LiNRR",
        nitrogen_source="15N2",
        catalyst="Cu",
        electrolyte="Li salt in THF",
        reactor_type="flow cell",
        potential=-0.2,
        FE_percent=61.0,
        EE_percent=None,
        NH3_yield=12.0,
        NH3_yield_unit="umol h-1 cm-2",
        stability=None,
        isotope_validation="yes",
        blank_control="unclear",
        contamination_control="unclear",
        nox_screening="unclear",
        detection_method="NMR",
        reliability_label="B",
        extraction_confidence="high",
        source_grounding_status="explicit",
        notes="test",
    )


class ExtractBenchSchemaTests(unittest.TestCase):
    def test_valid_record_round_trip(self) -> None:
        record = make_record()
        self.assertEqual(validate_extractbench_record(record), [])
        data = record_to_dict(record)
        self.assertEqual(record_from_dict(data).record_id, "E001")

    def test_invalid_allowed_value(self) -> None:
        data = record_to_dict(make_record())
        data["reaction_family"] = "bandgap"
        messages = validate_extractbench_record(data)
        self.assertTrue(any("reaction_family" in message for message in messages))

    def test_reliability_a_without_isotope_warns(self) -> None:
        data = record_to_dict(make_record())
        data["reliability_label"] = "A"
        data["isotope_validation"] = "unclear"
        messages = validate_extractbench_record(data)
        self.assertTrue(any("reliability_label A" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
