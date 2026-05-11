"""Lowest-level local document to Markdown conversion helpers."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_TEXT_FORMATS = {".md", ".txt"}
CONVERTER_CHOICES = {"auto", "docling", "markitdown", "pymupdf", "basic"}


def has_python_docx() -> bool:
    """Return whether the optional python-docx package is importable."""

    return importlib.util.find_spec("docx") is not None


def has_docling_cli() -> bool:
    """Return whether the optional docling CLI is available."""

    return shutil.which("docling") is not None


def has_docling_python() -> bool:
    """Return whether the optional docling Python API is importable."""

    return importlib.util.find_spec("docling") is not None


def has_markitdown_python() -> bool:
    """Return whether the optional MarkItDown Python package is importable."""

    return importlib.util.find_spec("markitdown") is not None


def has_pymupdf() -> bool:
    """Return whether the optional PyMuPDF package is importable."""

    return importlib.util.find_spec("fitz") is not None


def convert_local_document(
    input_path: str | Path,
    output_dir: str | Path = "input_markdown",
    converter: str = "auto",
    force: bool = False,
) -> dict[str, Any]:
    """Convert or copy one local document into Markdown for annotation."""

    source = Path(input_path)
    output_directory = Path(output_dir)
    suffix = source.suffix.lower()
    converter = converter.casefold()
    if converter not in CONVERTER_CHOICES:
        return _result(source, None, "error", suffix or "<none>", converter, None, None, None, f"Unknown converter: {converter}")

    try:
        if suffix == ".md":
            return _convert_markdown(source, output_directory, converter, force)
        if suffix == ".txt":
            return _convert_text(source, output_directory, converter, force)
        if suffix == ".docx":
            return _convert_rich_document(source, output_directory, converter, force)
        if suffix == ".pdf":
            return _convert_rich_document(source, output_directory, converter, force)
        return _result(
            source,
            None,
            "unsupported",
            suffix or "<none>",
            converter,
            None,
            None,
            None,
            f"Unsupported file format: {suffix or '<none>'}",
        )
    except Exception as exc:  # pragma: no cover - defensive return path
        return _result(source, None, "error", suffix or "<none>", converter, None, None, None, str(exc))


def convert_directory(
    input_dir: str | Path = "input_raw",
    output_dir: str | Path = "input_markdown",
    converter: str = "auto",
    force: bool = False,
    clean_output: bool = False,
) -> list[dict[str, Any]]:
    """Convert all non-hidden files in a directory into Markdown outputs."""

    directory = Path(input_dir)
    if not directory.exists():
        return []
    if clean_output:
        _clean_markdown_output(Path(output_dir))
    results: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        results.append(convert_local_document(path, output_dir, converter=converter, force=force))
    return results


def _convert_markdown(source: Path, output_directory: Path, converter_requested: str, force: bool) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    output_path = output_directory / source.name
    if output_path.exists() and not force and output_path.resolve() != source.resolve():
        existing = output_path.read_text(encoding="utf-8")
        return _result(source, output_path, "copied", ".md", converter_requested, "existing", None, len(existing), f"Existing Markdown retained at {output_path}")
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
        converter_requested,
        "basic",
        None,
        len(output_text),
        f"Markdown {status} to {output_path}",
    )


def _convert_text(source: Path, output_directory: Path, converter_requested: str, force: bool) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    output_path = output_directory / f"{source.stem}.md"
    if output_path.exists() and not force:
        existing = output_path.read_text(encoding="utf-8")
        return _result(source, output_path, "copied", ".txt", converter_requested, "existing", None, len(existing), f"Existing Markdown retained at {output_path}")
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _with_metadata_header(source, "basic", "converted", text),
        encoding="utf-8",
        newline="\n",
    )
    return _result(
        source,
        output_path,
        "converted",
        ".txt",
        converter_requested,
        "basic",
        None,
        len(text),
        f"Text converted to {output_path}",
    )


def _convert_rich_document(
    source: Path,
    output_directory: Path,
    converter_requested: str,
    force: bool,
) -> dict[str, Any]:
    output_path = output_directory / f"{source.stem}.md"
    if output_path.exists() and not force:
        existing = output_path.read_text(encoding="utf-8")
        return _result(source, output_path, "copied", source.suffix.lower(), converter_requested, "existing", None, len(existing), f"Existing Markdown retained at {output_path}")

    if converter_requested == "docling":
        return _convert_docling(source, output_directory, converter_requested)
    if converter_requested == "markitdown":
        return _convert_markitdown(source, output_directory, converter_requested)
    if converter_requested == "pymupdf":
        return _convert_pdf_pymupdf(source, output_directory, converter_requested)
    if converter_requested == "basic":
        return _convert_basic(source, output_directory, converter_requested)

    attempts = [
        _convert_docling,
        _convert_markitdown,
        _convert_basic,
    ]
    messages: list[str] = []
    for attempt in attempts:
        result = attempt(source, output_directory, converter_requested)
        if result["status"] in {"converted", "copied"}:
            if messages:
                result["message"] = result["message"] + " Previous attempts: " + " | ".join(messages)
            return result
        messages.append(f"{result.get('converter_used') or attempt.__name__}: {result['message']}")
    return _result(
        source,
        None,
        "unsupported",
        source.suffix.lower(),
        converter_requested,
        None,
        None,
        None,
        "No converter succeeded. " + " | ".join(messages),
    )


def _convert_docling(source: Path, output_directory: Path, converter_requested: str) -> dict[str, Any]:
    if has_docling_python():
        try:
            from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]

            result = DocumentConverter().convert(str(source))
            markdown = result.document.export_to_markdown()
            return _write_converted_markdown(
                source,
                output_directory,
                markdown,
                converter_requested,
                "docling",
                None,
                "Converted with Docling Python API",
            )
        except Exception as exc:
            if converter_requested == "docling" and not has_docling_cli():
                return _result(source, None, "error", source.suffix.lower(), converter_requested, "docling", None, None, f"Docling Python conversion failed: {exc}")

    if has_docling_cli():
        return _convert_docling_cli(source, output_directory, converter_requested)

    status = "error" if converter_requested == "docling" else "unsupported"
    return _result(
        source,
        None,
        status,
        source.suffix.lower(),
        converter_requested,
        "docling",
        None,
        None,
        "Docling is not installed.",
    )


def _convert_docling_cli(source: Path, output_directory: Path, converter_requested: str) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"{source.stem}.md"
    try:
        completed = subprocess.run(
            ["docling", str(source), "-o", str(output_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return _result(source, None, "error", source.suffix.lower(), converter_requested, "docling", None, None, f"Docling CLI failed to start: {exc}")
    if completed.returncode != 0:
        return _result(source, None, "error", source.suffix.lower(), converter_requested, "docling", None, None, f"Docling CLI failed: {completed.stderr.strip() or completed.stdout.strip()}")
    markdown = output_path.read_text(encoding="utf-8") if output_path.exists() else completed.stdout
    return _write_converted_markdown(
        source,
        output_directory,
        markdown,
        converter_requested,
        "docling",
        None,
        "Converted with Docling CLI",
    )


def _convert_markitdown(source: Path, output_directory: Path, converter_requested: str) -> dict[str, Any]:
    if not has_markitdown_python():
        status = "error" if converter_requested == "markitdown" else "unsupported"
        return _result(source, None, status, source.suffix.lower(), converter_requested, "markitdown", None, None, "MarkItDown is not installed.")
    try:
        from markitdown import MarkItDown  # type: ignore[import-not-found]

        result = MarkItDown().convert(str(source))
        markdown = getattr(result, "text_content", str(result))
    except Exception as exc:
        return _result(source, None, "error", source.suffix.lower(), converter_requested, "markitdown", None, None, f"MarkItDown conversion failed: {exc}")
    return _write_converted_markdown(
        source,
        output_directory,
        markdown,
        converter_requested,
        "markitdown",
        None,
        "Converted with MarkItDown Python package",
    )


def _convert_basic(source: Path, output_directory: Path, converter_requested: str) -> dict[str, Any]:
    if source.suffix.lower() == ".docx":
        return _convert_docx_basic(source, output_directory, converter_requested)
    if source.suffix.lower() == ".pdf":
        return _convert_pdf_pymupdf(source, output_directory, converter_requested)
    return _result(source, None, "unsupported", source.suffix.lower(), converter_requested, "basic", None, None, f"Basic converter does not support {source.suffix.lower()}")


def _convert_docx_basic(source: Path, output_directory: Path, converter_requested: str) -> dict[str, Any]:
    if not has_python_docx():
        return _result(
            source,
            None,
            "unsupported",
            ".docx",
            converter_requested,
            "basic",
            None,
            None,
            "Install python-docx to convert DOCX files.",
        )

    import docx  # type: ignore[import-not-found]

    document = docx.Document(str(source))
    paragraphs = [_format_docx_paragraph(paragraph) for paragraph in document.paragraphs if paragraph.text.strip()]
    body = "\n\n".join(paragraphs)
    return _write_converted_markdown(
        source,
        output_directory,
        body,
        converter_requested,
        "basic",
        None,
        "DOCX converted with python-docx basic converter",
    )


def _convert_pdf_pymupdf(source: Path, output_directory: Path, converter_requested: str) -> dict[str, Any]:
    if source.suffix.lower() != ".pdf":
        return _result(source, None, "unsupported", source.suffix.lower(), converter_requested, "pymupdf", None, None, "PyMuPDF converter only supports PDF files.")
    if not has_pymupdf():
        return _result(
            source,
            None,
            "unsupported",
            ".pdf",
            converter_requested,
            "pymupdf",
            None,
            None,
            "Install pymupdf to convert text-based PDF files.",
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
            converter_requested,
            "pymupdf",
            len(pages),
            len(plain_text),
            "PDF appears scanned or text extraction failed; use future Docling/OCR workflow.",
        )

    return _write_converted_markdown(
        source,
        output_directory,
        body,
        converter_requested,
        "pymupdf",
        len(pages),
        "Text-based PDF converted with PyMuPDF",
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
    converter_requested: str,
    converter_used: str | None,
    pages: int | None,
    characters: int | None,
    message: str,
) -> dict[str, Any]:
    return {
        "input_path": str(input_path),
        "output_path": str(output_path) if output_path is not None else None,
        "status": status,
        "format": file_format,
        "converter_requested": converter_requested,
        "converter_used": converter_used,
        "pages": pages,
        "characters": characters,
        "message": message,
    }


def _write_converted_markdown(
    source: Path,
    output_directory: Path,
    markdown: str,
    converter_requested: str,
    converter_used: str,
    pages: int | None,
    message: str,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"{source.stem}.md"
    output_text = _with_metadata_header(source, converter_used, "converted", markdown)
    output_path.write_text(output_text, encoding="utf-8", newline="\n")
    return _result(
        source,
        output_path,
        "converted",
        source.suffix.lower(),
        converter_requested,
        converter_used,
        pages,
        len(markdown),
        message,
    )


def _clean_markdown_output(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    for path in output_directory.glob("*.md"):
        if path.name == ".gitkeep":
            continue
        path.unlink()
