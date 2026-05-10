"""Lowest-level local document to Markdown conversion helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


SUPPORTED_TEXT_FORMATS = {".md", ".txt"}


def has_python_docx() -> bool:
    """Return whether the optional python-docx package is importable."""

    return importlib.util.find_spec("docx") is not None


def has_pymupdf() -> bool:
    """Return whether the optional PyMuPDF package is importable."""

    return importlib.util.find_spec("fitz") is not None


def convert_local_document(
    input_path: str | Path,
    output_dir: str | Path = "input_markdown",
) -> dict[str, Any]:
    """Convert or copy one local document into Markdown for annotation."""

    source = Path(input_path)
    output_directory = Path(output_dir)
    suffix = source.suffix.lower()

    try:
        if suffix == ".pdf":
            return _convert_pdf(source, output_directory)
        if suffix == ".docx":
            return _convert_docx(source, output_directory)
        if suffix == ".md":
            return _convert_markdown(source, output_directory)
        if suffix == ".txt":
            return _convert_text(source, output_directory)
        return _result(
            source,
            None,
            "unsupported",
            suffix or "<none>",
            f"Unsupported file format: {suffix or '<none>'}",
            None,
            None,
        )
    except Exception as exc:  # pragma: no cover - defensive return path
        return _result(source, None, "error", suffix or "<none>", str(exc), None, None)


def convert_directory(
    input_dir: str | Path = "input_raw",
    output_dir: str | Path = "input_markdown",
) -> list[dict[str, Any]]:
    """Convert all non-hidden files in a directory into Markdown outputs."""

    directory = Path(input_dir)
    if not directory.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        results.append(convert_local_document(path, output_dir))
    return results


def _convert_markdown(source: Path, output_directory: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    output_path = output_directory / source.name
    output_directory.mkdir(parents=True, exist_ok=True)
    status = "copied" if _has_metadata_header(text) else "converted"
    method = "markdown_copy" if status == "copied" else "markdown_with_metadata_header"
    output_text = text if _has_metadata_header(text) else _with_metadata_header(source, method, status, text)
    output_path.write_text(output_text, encoding="utf-8", newline="\n")
    return _result(
        source,
        output_path,
        status,
        ".md",
        f"Markdown {status} to {output_path}",
        None,
        len(output_text),
    )


def _convert_text(source: Path, output_directory: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    output_path = output_directory / f"{source.stem}.md"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _with_metadata_header(source, "txt_to_markdown", "converted", text),
        encoding="utf-8",
        newline="\n",
    )
    return _result(
        source,
        output_path,
        "converted",
        ".txt",
        f"Text converted to {output_path}",
        None,
        len(text),
    )


def _convert_docx(source: Path, output_directory: Path) -> dict[str, Any]:
    if not has_python_docx():
        return _result(
            source,
            None,
            "unsupported",
            ".docx",
            "Install python-docx to convert DOCX files.",
            None,
            None,
        )

    import docx  # type: ignore[import-not-found]

    document = docx.Document(str(source))
    paragraphs = [_format_docx_paragraph(paragraph) for paragraph in document.paragraphs if paragraph.text.strip()]
    output_path = output_directory / f"{source.stem}.md"
    output_directory.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(paragraphs)
    output_path.write_text(
        _with_metadata_header(source, "docx_to_markdown_python_docx", "converted", body),
        encoding="utf-8",
        newline="\n",
    )
    return _result(
        source,
        output_path,
        "converted",
        ".docx",
        f"DOCX converted to {output_path}",
        None,
        len(body),
    )


def _convert_pdf(source: Path, output_directory: Path) -> dict[str, Any]:
    if not has_pymupdf():
        return _result(
            source,
            None,
            "unsupported",
            ".pdf",
            "Install pymupdf to convert text-based PDF files.",
            None,
            None,
        )

    import fitz  # type: ignore[import-not-found]

    pages: list[str] = []
    extracted_texts: list[str] = []
    with fitz.open(str(source)) as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            extracted_texts.append(text)
            pages.append(f"## Page {index}\n\n{text}".rstrip())
    body = "\n\n".join(pages).strip()
    plain_text = "\n".join(extracted_texts).strip()
    if len(plain_text) < 20:
        return _result(
            source,
            None,
            "unsupported",
            ".pdf",
            "PDF appears scanned or text extraction failed; use future Docling/OCR workflow.",
            len(pages),
            len(plain_text),
        )

    output_path = output_directory / f"{source.stem}.md"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _with_metadata_header(source, "pdf_to_markdown_pymupdf", "converted", body),
        encoding="utf-8",
        newline="\n",
    )
    return _result(
        source,
        output_path,
        "converted",
        ".pdf",
        f"Text-based PDF converted to {output_path}",
        len(pages),
        len(plain_text),
    )


def _format_docx_paragraph(paragraph: Any) -> str:
    text = paragraph.text.strip()
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    if style_name.casefold().startswith("heading"):
        level = _heading_level(style_name)
        return f"{'#' * level} {text}"
    return text


def _heading_level(style_name: str) -> int:
    digits = "".join(character for character in style_name if character.isdigit())
    if not digits:
        return 2
    return max(1, min(6, int(digits)))


def _with_metadata_header(source: Path, method: str, status: str, body: str) -> str:
    header = "\n".join(
        [
            "---",
            f"source_file: {source}",
            f"source_format: {source.suffix.lower() or '<none>'}",
            f"conversion_method: {method}",
            f"conversion_status: {status}",
            "human_verification_required: true",
            'copyright_note: "Converted text is for local verification; do not publish full copyrighted text."',
            "---",
            "",
        ]
    )
    return header + body.strip() + "\n"


def _has_metadata_header(text: str) -> bool:
    return text.lstrip().startswith("---")


def _result(
    input_path: Path,
    output_path: Path | None,
    status: str,
    file_format: str,
    message: str,
    pages: int | None,
    characters: int | None,
) -> dict[str, Any]:
    return {
        "input_path": str(input_path),
        "output_path": str(output_path) if output_path is not None else None,
        "status": status,
        "format": file_format,
        "pages": pages,
        "characters": characters,
        "message": message,
    }
