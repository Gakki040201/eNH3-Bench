from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.chatextract_chain import (  # noqa: E402
    build_extraction_prompt,
    build_relevance_prompt,
    build_reliability_prompt,
    build_verification_prompt,
    run_rule_chatextract,
)


SPAN = (
    "A Li-mediated NRR experiment in THF with Li+ salt reported FE of 61% "
    "and an NH3 yield of 12 umol h-1 cm-2. 15N isotope labeling, Ar blank "
    "control, and NOx contamination checks were performed."
)


class ChatExtractChainTests(unittest.TestCase):
    def test_prompt_builders_include_source_span(self) -> None:
        record = {"reaction_family": "LiNRR", "FE_percent": 61.0}
        self.assertIn(SPAN, build_relevance_prompt(SPAN))
        self.assertIn("Return one JSON object", build_extraction_prompt(SPAN))
        self.assertIn(SPAN, build_verification_prompt(SPAN, record))
        self.assertIn("reliability label", build_reliability_prompt(SPAN, record).casefold())

    def test_rule_chatextract_extracts_core_fields(self) -> None:
        record = run_rule_chatextract({"span_id": "S001", "paper_id": "P001", "text": SPAN})
        self.assertEqual(record["method_name"], "enh3_chatextract_rule")
        self.assertEqual(record["record_id"], "E001")
        self.assertEqual(record["reaction_family"], "LiNRR")
        self.assertEqual(record["isotope_validation"], "yes")
        self.assertEqual(record["blank_control"], "yes")
        self.assertEqual(record["contamination_control"], "yes")
        self.assertEqual(record["FE_percent"], 61.0)
        self.assertIn(record["extraction_confidence"], {"medium", "high"})
        self.assertIn(record["source_span"], SPAN)


if __name__ == "__main__":
    unittest.main()
