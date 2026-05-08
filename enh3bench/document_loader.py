"""Local Markdown document loading utilities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def load_markdown_documents(input_dir: str | Path) -> list[dict[str, Any]]:
    """Load Markdown files from a directory as plain local documents."""

    directory = Path(input_dir)
    documents: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == ".gitkeep":
            continue
        documents.append(
            {
                "document_id": path.stem,
                "path": str(path),
                "text": path.read_text(encoding="utf-8"),
            }
        )
    return documents


def split_into_paragraphs(text: str) -> list[str]:
    """Split Markdown text into non-empty paragraph blocks."""

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", text)]
    return [paragraph for paragraph in paragraphs if paragraph]
