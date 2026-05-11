from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_external_reuse_log import parse_reuse_log, validate_reuse_log  # noqa: E402


HEADER = (
    "| date | external_repo | license | external_file_or_component | local_file | "
    "copied_code | adaptation_type | attribution_action | notes |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


class ExternalReuseLogTests(unittest.TestCase):
    def test_parser_reads_temp_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "log.md"
            path.write_text(
                "# Log\n\n" + HEADER + "| initial | repo | MIT | idea | pending | no | conceptual | docs | none |\n",
                encoding="utf-8",
            )
            rows = parse_reuse_log(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["copied_code"], "no")

    def test_copied_code_yes_without_attribution_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "log.md"
            path.write_text(
                "# Log\n\n" + HEADER + "| today | repo | Apache-2.0 | file.py | pending | yes | copied |  | none |\n",
                encoding="utf-8",
            )
            errors = validate_reuse_log(path)
            self.assertTrue(errors)

    def test_copied_code_no_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "log.md"
            path.write_text(
                "# Log\n\n" + HEADER + "| today | repo | Apache-2.0 | idea | pending | no | conceptual | docs | none |\n",
                encoding="utf-8",
            )
            self.assertEqual(validate_reuse_log(path), [])


if __name__ == "__main__":
    unittest.main()
