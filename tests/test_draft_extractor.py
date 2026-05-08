from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.draft_extractor import draft_evidence_from_span  # noqa: E402


class DraftExtractorTests(unittest.TestCase):
    def test_draft_contains_source_span_and_machine_fields(self) -> None:
        span = {
            "span_id": "S007_1",
            "paper_id": "P007",
            "document_id": "P007",
            "source_section": "results",
            "text": "Li-mediated N2 reduction produced NH3 at 10.5 nmol s-1 cm-2 with 62% FE and 15N2 isotope labeling.",
        }
        draft = draft_evidence_from_span(span)
        self.assertEqual(draft["evidence_id"], "E007_1")
        self.assertEqual(draft["source_span"], span["text"])
        self.assertEqual(draft["reaction_family"], "LiNRR")
        self.assertIn(draft["draft_confidence"], {"medium", "high"})
        self.assertEqual(draft["machine_notes"], "Machine draft; requires human verification.")


if __name__ == "__main__":
    unittest.main()
