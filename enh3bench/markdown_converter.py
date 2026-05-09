"""Lowest-level local document to Markdown conversion helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_TEXT_FORMATS = {".md", ".txt"}


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
            return _result(
                source,
                None,
                "unsupported",
                suffix,
                "PDF conversion is deferred; manually convert to Markdown or use future Docling adapter.",
            )
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
        )
    except Exception as exc:  # pragma: no cover - defensive return path
        return _result(source, None, "error", suffix or "<none>", str(exc))


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
    return _result(source, output_path, status, ".md", f"Markdown {status} to {output_path}")


def _convert_text(source: Path, output_directory: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    output_path = output_directory / f"{source.stem}.md"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _with_metadata_header(source, "txt_to_markdown", "converted", text),
        encoding="utf-8",
        newline="\n",
    )
    return _result(source, output_path, "converted", ".txt", f"Text converted to {output_path}")


def _convert_docx(source: Path, output_directory: Path) -> dict[str, Any]:
    try:
        import docx  # type: ignore[import-not-found]
    except ImportError:
        return _result(
            source,
            None,
            "unsupported",
            ".docx",
            "DOCX conversion requires optional package python-docx; install it outside the benchmark core if needed.",
        )

    document = docx.Document(str(source))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    output_path = output_directory / f"{source.stem}.md"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _with_metadata_header(source, "docx_to_markdown_python_docx", "converted", "\n\n".join(paragraphs)),
        encoding="utf-8",
        newline="\n",
    )
    return _result(source, output_path, "converted", ".docx", f"DOCX converted to {output_path}")


def _with_metadata_header(source: Path, method: str, status: str, body: str) -> str:
    header = "\n".join(
        [
            "---",
            f"source_file: {source}",
            f"conversion_method: {method}",
            f"conversion_status: {status}",
            "human_verification_required: true",
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
) -> dict[str, Any]:
    return {
        "input_path": str(input_path),
        "output_path": str(output_path) if output_path is not None else None,
        "status": status,
        "format": file_format,
        "message": message,
    }
