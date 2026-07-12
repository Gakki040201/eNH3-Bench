import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.download_oa_papers_from_master import (
    Candidate,
    download_pdf,
    is_journal_record,
    is_supplementary_doi,
    make_filename,
    normalize_doi,
    ordered_candidates,
    paper_id_number,
    process_record,
    valid_pdf,
    write_manifests,
)


class FakeDownloadResponse:
    def __init__(self, body, content_type="application/pdf", status_code=200):
        self.body = body
        self.status_code = status_code
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, chunk_size=65536):
        yield self.body


class DownloadOAPapersTests(unittest.TestCase):
    def test_numeric_paper_id_ordering_places_p0009_before_p0010(self):
        values = ["P0010", "P0002", "P0009", "P0001"]
        self.assertEqual(sorted(values, key=paper_id_number), ["P0001", "P0002", "P0009", "P0010"])

    def test_doi_normalization(self):
        self.assertEqual(normalize_doi(" HTTPS://doi.org/10.1038/ABC.123. "), "10.1038/abc.123")
        self.assertEqual(normalize_doi("doi: 10.1000/XYZ"), "10.1000/xyz")

    def test_synthesis_is_not_mistaken_for_thesis(self):
        self.assertTrue(is_journal_record({"Article_Type": "Synthesis Article", "Journal": "Catalysis Today"}))
        self.assertFalse(is_journal_record({"Article_Type": "PhD Thesis", "Journal": "Repository"}))

    def test_supplementary_doi_exclusion(self):
        self.assertTrue(is_supplementary_doi("10.1021/acsenergylett.0c00924.s001"))
        self.assertTrue(is_supplementary_doi("10.1000/article-supp"))
        self.assertFalse(is_supplementary_doi("10.1000/article"))

    def test_filename_sanitization(self):
        record = {"Paper_ID": "P0001", "Authors": "Doe, Jane; Roe, R.", "Year": 2024,
                  "Title": 'A <bad>: title / with * Windows? characters'}
        name = make_filename(record)
        self.assertEqual(name, "P0001_Doe_2024_A_bad_title_with_Windows_characters.pdf")
        self.assertFalse(any(char in name for char in '<>:"/\\|?*'))

    def test_existing_valid_pdf_is_skipped_without_metadata_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            record = {"Paper_ID": "P0001", "Authors": "Jane Doe", "Year": 2024,
                      "Title": "A paper", "DOI": "10.1000/test", "Journal": "Journal"}
            path = output / make_filename(record)
            path.write_bytes(b"%PDF-" + b"x" * 1024)
            args = self.args(output)
            session = Mock()
            row = process_record(record, 1, args, session, output)
            self.assertEqual(row["status"], "skipped_existing")
            session.get.assert_not_called()

    def test_html_response_is_rejected_and_part_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "paper.pdf"
            session = Mock()
            session.get.return_value = FakeDownloadResponse(b"<html>login</html>" * 100, "text/html")
            with self.assertRaisesRegex(ValueError, "%PDF"):
                download_pdf(session, Candidate("https://example.test/paper" , "test"), destination, 2, 1)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".pdf.part").exists())

    def test_invalid_non_pdf_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.pdf"
            path.write_bytes(b"NOT-A-PDF" + b"x" * 2000)
            self.assertFalse(valid_pdf(path))

    def test_publisher_published_version_precedes_repository(self):
        repository = Candidate("https://repo.test/a.pdf", "unpaywall", host_type="repository", version="publishedVersion")
        publisher = Candidate("https://publisher.test/a.pdf", "openalex", host_type="publisher", version="publishedVersion")
        self.assertEqual(ordered_candidates([repository, publisher])[0], publisher)

    def test_manifests_are_atomically_written_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "manifest.csv"
            jsonl_path = Path(tmp) / "manifest.jsonl"
            row = {"sequence": 1, "paper_id": "P0001", "status": "not_oa", "attempted_urls": []}
            write_manifests({"P0001": row}, csv_path, jsonl_path)
            self.assertTrue(csv_path.is_file())
            self.assertTrue(jsonl_path.is_file())
            self.assertIn("P0001", csv_path.read_text(encoding="utf-8-sig"))

    @patch("scripts.download_oa_papers_from_master.download_pdf")
    @patch("scripts.download_oa_papers_from_master.resolve_oa")
    def test_dry_run_performs_no_network_download(self, resolve, download):
        from scripts.download_oa_papers_from_master import Resolution
        resolve.return_value = Resolution(True, "gold", [Candidate("https://example.test/a.pdf", "unpaywall")], [])
        with tempfile.TemporaryDirectory() as tmp:
            record = {"Paper_ID": "P0001", "Authors": "Jane Doe", "Year": 2024,
                      "Title": "A paper", "DOI": "10.1000/test", "Journal": "Journal"}
            args = self.args(Path(tmp))
            args.dry_run = True
            row = process_record(record, 1, args, Mock(), Path(tmp))
        self.assertEqual(row["status"], "dry_run_selected")
        download.assert_not_called()

    @staticmethod
    def args(output):
        return argparse.Namespace(output_dir=output, overwrite=False, unpaywall_email="test@example.org",
                                  timeout=2.0, no_openalex=False, no_prefer_publisher=False,
                                  max_file_mb=1.0, dry_run=False)


if __name__ == "__main__":
    unittest.main()
