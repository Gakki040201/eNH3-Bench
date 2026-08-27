from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .schema import FigureContentType, FigureRecord, file_sha256


CAPTION_RE = re.compile(
    r"^\s*(?:\d{1,3}\s+)?((?:Extended\s+Data\s+|Supplementary\s+)?(?:Figure(?!s\b)|Fig\.)\s*(?:S\s*)?\d+[A-Za-z]?)\b(?=\s*[.:])",
    re.IGNORECASE,
)
PANEL_RE = re.compile(r"^\s*\(?([a-z])\)?\s*$", re.IGNORECASE)


def _fitz():
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required for figure location") from exc
    return fitz


def locate_figures(
    pdf_path: str | Path,
    *,
    paper_id: str,
    bundle_id: str,
    source_asset_id: str,
) -> list[FigureRecord]:
    """Locate captions from exact PDF text geometry and associate regions above them."""
    fitz = _fitz()
    path = Path(pdf_path)
    digest = file_sha256(path)
    records: list[FigureRecord] = []
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            captions = _caption_lines(page)
            for caption_index, (caption_bbox, caption, label) in enumerate(captions):
                prior_bottom = captions[caption_index - 1][0][3] if caption_index else 0.0
                next_top = captions[caption_index + 1][0][1] if caption_index + 1 < len(captions) else float(page.rect.height)
                above = (0.0, max(prior_bottom, 0.0), float(page.rect.width), caption_bbox[1])
                below = (0.0, caption_bbox[3], float(page.rect.width), next_top)
                candidates = [item for item in (above, below) if item[3] - item[1] >= 24]
                if not candidates:
                    continue
                # Captions are commonly below article figures but above SI
                # figures. Select by local PDF graphical content, not layout
                # convention. Ties retain the conventional above-caption area.
                bbox = max(candidates, key=lambda item: (_content_score(page, item), item == above))
                content_type = classify_figure_content(page, bbox)
                panels = _panel_candidates(page, bbox)
                if not panels:
                    records.append(FigureRecord(
                        paper_id=paper_id, bundle_id=bundle_id, source_asset_id=source_asset_id,
                        source_file_sha256=digest, page=page_index + 1, figure_label=label,
                        caption=caption, caption_bbox=caption_bbox, figure_bbox=bbox,
                        figure_content_type=content_type,
                    ))
                else:
                    for panel_label, panel_bbox in panels:
                        records.append(FigureRecord(
                            paper_id=paper_id, bundle_id=bundle_id, source_asset_id=source_asset_id,
                            source_file_sha256=digest, page=page_index + 1, figure_label=label,
                            caption=caption, caption_bbox=caption_bbox, figure_bbox=bbox,
                            panel_label=panel_label, panel_bbox=panel_bbox,
                            figure_content_type=content_type,
                        ))
    unique = {
        (item.paper_id, item.bundle_id, item.source_asset_id, item.page, item.figure_label, item.figure_bbox, item.panel_label, item.panel_bbox): item
        for item in records
    }
    return sorted(unique.values(), key=lambda item: (item.page, item.figure_label, item.panel_label or ""))


def _caption_lines(page: Any) -> list[tuple[tuple[float, float, float, float], str, str]]:
    lines: list[tuple[tuple[float, float, float, float], str]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(str(span.get("text") or "") for span in line.get("spans", []))
            text = " ".join(text.split())
            if text:
                lines.append((tuple(float(value) for value in line["bbox"]), text))
    lines.sort(key=lambda item: (item[0][1], item[0][0]))
    captions = []
    for bbox, text in lines:
        match = CAPTION_RE.match(text)
        if match:
            captions.append((bbox, text[match.start(1):], _normalize_label(match.group(1))))
    return captions


def _content_score(page: Any, bbox: tuple[float, float, float, float]) -> int:
    fitz = _fitz()
    region = fitz.Rect(bbox)
    drawing_score = 0
    for drawing in page.get_cdrawings():
        rect = fitz.Rect(drawing["rect"])
        if rect.intersects(region) or region.contains(rect.tl) or region.contains(rect.br):
            drawing_score += 1
    image_score = sum(5 for image in page.get_images(full=True) if any(rect.intersects(region) for rect in page.get_image_rects(image[0])))
    return drawing_score + image_score


def classify_figure_content(page: Any, bbox: tuple[float, float, float, float]) -> FigureContentType:
    fitz = _fitz()
    region = fitz.Rect(bbox)
    drawing_count = sum(1 for drawing in page.get_cdrawings() if fitz.Rect(drawing["rect"]).intersects(region))
    image_count = sum(1 for image in page.get_images(full=True) if any(rect.intersects(region) for rect in page.get_image_rects(image[0])))
    if drawing_count and image_count:
        return FigureContentType.MIXED
    if drawing_count:
        return FigureContentType.VECTOR
    if image_count:
        return FigureContentType.RASTER
    return FigureContentType.UNKNOWN


def _panel_candidates(page: Any, bbox: tuple[float, float, float, float]) -> list[tuple[str, tuple[float, float, float, float]]]:
    fitz = _fitz()
    region = fitz.Rect(bbox)
    labels: list[tuple[str, float, float]] = []
    for word in page.get_text("words", clip=region):
        match = PANEL_RE.match(str(word[4]))
        if match and len(str(word[4])) <= 3:
            labels.append((match.group(1).lower(), float(word[0]), float(word[1])))
    labels = sorted({item for item in labels}, key=lambda item: (item[2], item[1]))
    if len(labels) < 2:
        return []
    # Conservative grid split; unresolved/overlapping panels remain one figure.
    xs = sorted({round(item[1], 1) for item in labels})
    ys = sorted({round(item[2], 1) for item in labels})
    if len(xs) * len(ys) != len(labels):
        return []
    x_edges = _edges(xs, bbox[0], bbox[2])
    y_edges = _edges(ys, bbox[1], bbox[3])
    result = []
    for label, x, y in labels:
        xi = min(range(len(xs)), key=lambda index: abs(xs[index] - x))
        yi = min(range(len(ys)), key=lambda index: abs(ys[index] - y))
        result.append((label, (x_edges[xi], y_edges[yi], x_edges[xi + 1], y_edges[yi + 1])))
    return result


def _edges(values: list[float], lower: float, upper: float) -> list[float]:
    return [lower] + [(left + right) / 2 for left, right in zip(values, values[1:])] + [upper]


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("Fig.", "Figure", 1), flags=re.IGNORECASE).strip()
