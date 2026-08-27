from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .calibration import PdfPixelTransform
from .schema import BBox


def _fitz():
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required for local PDF rendering") from exc
    return fitz


@dataclass(frozen=True)
class RenderResult:
    path: Path
    transform: PdfPixelTransform


def render_bbox(pdf_path: str | Path, page_number: int, bbox: BBox, output_path: str | Path, *, dpi: int) -> RenderResult:
    fitz = _fitz()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as document:
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), clip=fitz.Rect(bbox), alpha=False)
        pixmap.save(output)
    return RenderResult(output, PdfPixelTransform.for_bbox(bbox, dpi, pixmap.width, pixmap.height))


@dataclass(frozen=True)
class ExternalExtractorResult:
    extractor: str
    version: str | None
    result: str
    decline_reason: str | None
    agreement_with_native: float | None = None
    output_path: str | None = None

    def to_dict(self) -> dict[str, object | None]:
        return self.__dict__.copy()


def model_checksum(path: str | Path) -> str | None:
    target = Path(path)
    if not target.is_file():
        return None
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_subprocess_adapter(
    *, extractor: str, command: Iterable[str], output_json: str | Path, cwd: str | Path | None = None, timeout: int = 900,
) -> ExternalExtractorResult:
    command = list(command)
    if not command:
        return ExternalExtractorResult(extractor, None, "DECLINED", "no adapter command configured")
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ExternalExtractorResult(extractor, None, "DECLINED", str(exc))
    output = Path(output_json)
    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout or f"exit {completed.returncode}").strip()[-1000:]
        return ExternalExtractorResult(extractor, None, "DECLINED", reason)
    if not output.is_file():
        return ExternalExtractorResult(extractor, None, "DECLINED", "adapter produced no JSON result")
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ExternalExtractorResult(extractor, None, "DECLINED", f"invalid adapter JSON: {exc}")
    return ExternalExtractorResult(extractor, str(payload.get("version") or "unknown"), str(payload.get("result") or "OK"), payload.get("decline_reason"), output_path=str(output))


def availability_report(third_party_root: str | Path) -> list[dict[str, object | None]]:
    root = Path(third_party_root)
    specifications = {
        "pdf2plot": root / "pdf2plot",
        "pdf-mcp": root / "pdf-mcp",
        "AutoLineDigitizer": root / "AutoLineDigitizer",
        "extract-line-chart-data": root / "extract-line-chart-data",
        "AutoPlot-Digitizer": root / "AutoPlot-Digitizer",
        "PlotDigitizer": root / "PlotDigitizer",
    }
    rows = []
    for name, path in specifications.items():
        commit = _git_commit(path)
        model_paths = sorted(path.rglob("*.pth")) if path.is_dir() else []
        rows.append({
            "extractor": name,
            "repo_path": str(path),
            "repo_commit": commit,
            "available": path.is_dir() and commit is not None,
            "model_files": [{"path": str(item), "sha256": model_checksum(item)} for item in model_paths],
            "scientific_run_available": name in {"pdf2plot", "pdf-mcp", "PlotDigitizer"} or bool(model_paths),
            "decline_reason": None if name in {"pdf2plot", "pdf-mcp", "PlotDigitizer"} or model_paths else "required isolated environment/model weights not installed",
        })
    return rows


def _git_commit(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    completed = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None
