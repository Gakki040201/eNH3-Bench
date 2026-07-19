from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from enh3bench.cleanroom_schema import (
    CLEANROOM_PROFILE,
    CLEANROOM_SCHEMA_VERSION,
    PAPER_ADMISSIBILITY_STATUSES,
    common_fields,
    atomic_write_text,
    validate_record,
)


class CleanroomSchemaTests(unittest.TestCase):
    def test_independent_schema_and_profile(self) -> None:
        self.assertEqual(CLEANROOM_SCHEMA_VERSION, "0.15-cleanroom.1")
        self.assertEqual(CLEANROOM_PROFILE, "document_first_cleanroom_v1")

    def test_common_fields_are_explicit(self) -> None:
        fields = common_fields("run", "documents")
        self.assertEqual(set(fields), {"schema_version", "pipeline_profile", "run_name", "record_created_by_stage"})

    def test_paper_statuses_exclude_overclaims(self) -> None:
        self.assertNotIn("fully_validated", PAPER_ADMISSIBILITY_STATUSES)
        self.assertNotIn("scientifically_comparable", PAPER_ADMISSIBILITY_STATUSES)

    def test_missing_document_fields_fail_validation(self) -> None:
        self.assertIn("missing_field:paper_id", validate_record("document", common_fields("run", "documents")))

    def test_wrong_profile_fails_validation(self) -> None:
        record = common_fields("run", "documents")
        record["pipeline_profile"] = "legacy"
        self.assertIn("invalid_pipeline_profile", validate_record("document", record))

    def test_atomic_write_failure_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "ledger.jsonl"
            destination.write_text("original\n", encoding="utf-8")
            with patch("enh3bench.cleanroom_schema._replace_with_retry", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    atomic_write_text(destination, "replacement\n")
            self.assertEqual(destination.read_text(encoding="utf-8"), "original\n")
            self.assertEqual([path for path in destination.parent.iterdir() if path != destination], [])


if __name__ == "__main__":
    unittest.main()
