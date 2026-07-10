"""Local Markdown document loading utilities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from enh3bench.front_matter import make_front_matter_records, strip_conversion_front_matter


def load_markdown_documents(input_dir: str | Path) -> list[dict[str, Any]]:
    """Load Markdown files from a directory as plain local documents."""

    directory = Path(input_dir)
    documents: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == ".gitkeep":
            continue
        raw_text = path.read_text(encoding="utf-8")
        isolation = strip_conversion_front_matter(raw_text)
        document_id = path.stem
        documents.append(
            {
                "document_id": document_id,
                "path": str(path),
                "text": isolation["body_text"],
                "raw_text": raw_text,
                "front_matter_metadata_text": isolation["metadata_text"],
                "repository_cover_text": isolation["repository_cover_text"],
                "front_matter_signals": isolation["signals"],
                "metadata_removed": isolation["metadata_removed"],
                "repository_cover_removed": isolation["repository_cover_removed"],
                "front_matter_records": make_front_matter_records(document_id, document_id, isolation),
            }
        )
    return documents


def split_into_paragraphs(text: str) -> list[str]:
    """Split Markdown text into non-empty paragraph blocks."""

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", text)]
    return [paragraph for paragraph in paragraphs if paragraph]
