from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .calibration import AxisCalibration, CalibrationAnchor
from .calibration import PdfPixelTransform
from .schema import (
    AxisScale,
    ExtractionManifest,
    ExtractionStatus,
    FigurePoint,
    FigureRecord,
    MeasurementSourceClass,
)


NUMERIC_RE = re.compile(r"^[−+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?%?$")


def _fitz():
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required for vector extraction") from exc
    return fitz


@dataclass(frozen=True)
class VectorPath:
    path_id: str
    bbox: tuple[float, float, float, float]
    points: tuple[tuple[float, float], ...]
    color: tuple[float, ...] | None
    fill: tuple[float, ...] | None
    width: float
    dashes: str | None
    closed: bool

    @property
    def length(self) -> float:
        return sum(math.dist(left, right) for left, right in zip(self.points, self.points[1:]))

    def style_key(self) -> tuple[object, ...]:
        color = tuple(round(value, 3) for value in self.color) if self.color else None
        return color, round(self.width, 2), self.dashes or ""

    def to_dict(self) -> dict[str, object]:
        return {"path_id": self.path_id, "bbox": list(self.bbox), "points": [list(item) for item in self.points], "color": self.color, "fill": self.fill, "width": self.width, "dashes": self.dashes, "closed": self.closed, "length": self.length}


def inventory_paths(pdf_path: str | Path, page_number: int, bbox: Iterable[float]) -> list[VectorPath]:
    fitz = _fitz()
    region = fitz.Rect(tuple(bbox))
    result: list[VectorPath] = []
    with fitz.open(pdf_path) as document:
        page = document[page_number - 1]
        for index, drawing in enumerate(page.get_drawings()):
            drawing_rect = fitz.Rect(drawing["rect"])
            points = _drawing_points(drawing)
            if len(points) < 2:
                continue
            # PyMuPDF represents perfectly horizontal/vertical strokes with a
            # zero-height/zero-width Rect; Rect.intersects() returns False for
            # those degenerate rectangles even when the stroke is in-region.
            if not drawing_rect.intersects(region) and not any(region.contains(fitz.Point(*point)) for point in points):
                continue
            result.append(VectorPath(
                path_id=f"p{page_number:04d}-v{index:06d}", bbox=tuple(float(value) for value in drawing_rect),
                points=tuple(points), color=_color(drawing.get("color")), fill=_color(drawing.get("fill")),
                width=float(drawing.get("width") or 0), dashes=drawing.get("dashes"),
                closed=bool(drawing.get("closePath")),
            ))
    return result


def _drawing_points(drawing: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for item in drawing.get("items", []):
        operator = item[0]
        values = item[1:]
        if operator == "l":
            for point in values[:2]:
                _append_point(points, point)
        elif operator == "c":
            for point in values:
                _append_point(points, point)
        elif operator == "re":
            rect = values[0]
            for point in ((rect.x0, rect.y0), (rect.x1, rect.y0), (rect.x1, rect.y1), (rect.x0, rect.y1), (rect.x0, rect.y0)):
                _append_point(points, point)
        elif operator == "qu":
            quad = values[0]
            for point in (quad.ul, quad.ur, quad.lr, quad.ll, quad.ul):
                _append_point(points, point)
    return points


def _append_point(target: list[tuple[float, float]], value: Any) -> None:
    if hasattr(value, "x") and hasattr(value, "y"):
        point = (round(float(value.x), 6), round(float(value.y), 6))
        if not target or target[-1] != point:
            target.append(point)


def _color(value: Any) -> tuple[float, ...] | None:
    return tuple(float(item) for item in value) if value is not None else None


def detect_axis_candidates(paths: Iterable[VectorPath], bbox: Iterable[float]) -> dict[str, list[VectorPath]]:
    x0, y0, x1, y1 = tuple(bbox)
    width, height = x1 - x0, y1 - y0
    horizontal, vertical = [], []
    for path in paths:
        if len(path.points) < 2:
            continue
        px0, py0 = path.points[0]
        px1, py1 = path.points[-1]
        if abs(py1 - py0) <= max(0.5, path.width) and abs(px1 - px0) >= width * 0.25:
            horizontal.append(path)
        if abs(px1 - px0) <= max(0.5, path.width) and abs(py1 - py0) >= height * 0.25:
            vertical.append(path)
    return {"x": sorted(horizontal, key=lambda item: (abs(item.bbox[3] - y1), -item.length)), "y": sorted(vertical, key=lambda item: (abs(item.bbox[0] - x0), -item.length))}


def text_tick_candidates(pdf_path: str | Path, page_number: int, plot_bbox: Iterable[float]) -> dict[str, list[CalibrationAnchor]]:
    fitz = _fitz()
    x0, y0, x1, y1 = tuple(plot_bbox)
    x_values: list[tuple[CalibrationAnchor, float]] = []
    y_values: list[tuple[CalibrationAnchor, float]] = []
    with fitz.open(pdf_path) as document:
        page = document[page_number - 1]
        clip = fitz.Rect(max(0, x0 - 100), max(0, y0 - 30), min(page.rect.width, x1 + 30), min(page.rect.height, y1 + 80))
        for word in page.get_text("words", clip=clip):
            raw = str(word[4]).strip().replace("−", "-").rstrip("%")
            if not NUMERIC_RE.match(str(word[4]).strip()):
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            cx, cy = (word[0] + word[2]) / 2, (word[1] + word[3]) / 2
            if y1 - 8 <= cy <= y1 + 55 and x0 - 8 <= cx <= x1 + 8:
                x_values.append((CalibrationAnchor(float(cx), value), float(cy)))
            if x0 - 80 <= cx <= x0 + 8 and y0 - 8 <= cy <= y1 + 8:
                y_values.append((CalibrationAnchor(float(cy), value), float(cx)))
    return {"x": _dominant_text_band(x_values), "y": _dominant_text_band(y_values)}


def _dominant_text_band(values: list[tuple[CalibrationAnchor, float]], tolerance: float = 4.0) -> list[CalibrationAnchor]:
    """Keep the tick-label row/column with the strongest geometric support."""
    if not values:
        return []
    bands: list[list[tuple[CalibrationAnchor, float]]] = []
    for item in sorted(values, key=lambda value: value[1]):
        matching = next((band for band in bands if abs(sum(entry[1] for entry in band) / len(band) - item[1]) <= tolerance), None)
        (matching if matching is not None else bands.append([]) or bands[-1]).append(item)
    best = max(bands, key=lambda band: (len(band), -sum(item[1] for item in band) / len(band)))
    return _dedupe_anchors([item[0] for item in best])


def _dedupe_anchors(values: list[CalibrationAnchor]) -> list[CalibrationAnchor]:
    unique = {(round(item.coordinate, 3), item.value): item for item in values}
    return sorted(unique.values(), key=lambda item: item.coordinate)


def infer_calibration(anchors: list[CalibrationAnchor]) -> AxisCalibration:
    if len(anchors) < 2:
        raise ValueError("ambiguous axis: fewer than two exact PDF tick labels")
    linear = AxisCalibration.fit(anchors, AxisScale.LINEAR)
    candidates = [linear]
    if all(item.value > 0 for item in anchors):
        candidates.append(AxisCalibration.fit(anchors, AxisScale.LOG))
    candidates.sort(key=lambda item: item.rms_residual)
    if len(candidates) > 1 and abs(candidates[0].rms_residual - candidates[1].rms_residual) < 1e-9 and len(anchors) == 2:
        raise ValueError("ambiguous axis scale: two anchors cannot distinguish linear from log")
    return candidates[0]


def group_series(paths: Iterable[VectorPath], plot_bbox: Iterable[float], *, minimum_points: int = 3) -> dict[str, list[VectorPath]]:
    x0, y0, x1, y1 = tuple(plot_bbox)
    groups: dict[tuple[object, ...], list[VectorPath]] = defaultdict(list)
    for path in paths:
        if len(path.points) < minimum_points or path.length <= 0:
            continue
        inside = sum(1 for x, y in path.points if x0 <= x <= x1 and y0 <= y <= y1)
        if inside / len(path.points) < 0.8:
            continue
        groups[path.style_key()].append(path)
    ordered = sorted(groups.values(), key=lambda values: (-sum(item.length for item in values), values[0].style_key()))
    return {f"series-{index:03d}": values for index, values in enumerate(ordered, start=1)}


def plot_bbox_from_axes(paths: Iterable[VectorPath], figure_bbox: Iterable[float]) -> tuple[float, float, float, float] | None:
    axes = detect_axis_candidates(paths, figure_bbox)
    if not axes["x"] or not axes["y"]:
        return None
    horizontal, vertical = axes["x"][0], axes["y"][0]
    left = vertical.points[0][0]
    bottom = horizontal.points[0][1]
    right = max(point[0] for point in horizontal.points)
    top = min(point[1] for point in vertical.points)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def inventory_figure(pdf_path: str | Path, figure: FigureRecord) -> dict[str, object]:
    bbox = figure.panel_bbox or figure.figure_bbox
    paths = inventory_paths(pdf_path, figure.page, bbox)
    plot_bbox = plot_bbox_from_axes(paths, bbox)
    return {
        "path_count": len(paths),
        "paths": [item.to_dict() for item in paths],
        "plot_bbox": list(plot_bbox) if plot_bbox else None,
        "series_groups": {key: [item.path_id for item in value] for key, value in group_series(paths, plot_bbox or bbox).items()},
    }


def recover_vector_points(
    pdf_path: str | Path,
    figure: FigureRecord,
    *,
    transform: PdfPixelTransform,
    extractor_version: str,
) -> tuple[ExtractionManifest, dict[str, object]]:
    """Recover path vertices when axes are exact and series separation is unambiguous.

    PDF geometry and born-digital tick text are the only numeric inputs here. A
    multi-series result without deterministic legend labels is retained for
    review, never promoted automatically.
    """
    bbox = figure.panel_bbox or figure.figure_bbox
    paths = inventory_paths(pdf_path, figure.page, bbox)
    plot_bbox = plot_bbox_from_axes(paths, bbox)
    decline: list[str] = []
    if plot_bbox is None:
        decline.append("axis geometry is ambiguous")
        return ExtractionManifest(figure, "enh3bench-pymupdf-vector", extractor_version, ExtractionStatus.REVIEW_REQUIRED, decline), {"plot_bbox": None}
    tick_candidates = text_tick_candidates(pdf_path, figure.page, plot_bbox)
    try:
        x_calibration = infer_calibration(tick_candidates["x"])
        y_calibration = infer_calibration(tick_candidates["y"])
    except ValueError as exc:
        decline.append(str(exc))
        return ExtractionManifest(figure, "enh3bench-pymupdf-vector", extractor_version, ExtractionStatus.REVIEW_REQUIRED, decline), {
            "plot_bbox": list(plot_bbox), "tick_candidates": {key: [item.__dict__ for item in value] for key, value in tick_candidates.items()},
        }
    groups = group_series(paths, plot_bbox)
    if not groups:
        decline.append("vector paths cannot be separated from axes and decoration")
        return ExtractionManifest(figure, "enh3bench-pymupdf-vector", extractor_version, ExtractionStatus.REVIEW_REQUIRED, decline), {"plot_bbox": list(plot_bbox)}
    if len(groups) > 1:
        decline.append("legend/series mapping requires review")
    points: list[FigurePoint] = []
    for series_id, group in groups.items():
        ordered_pdf_points: list[tuple[float, float]] = []
        for path in group:
            for point in path.points:
                if plot_bbox[0] <= point[0] <= plot_bbox[2] and plot_bbox[1] <= point[1] <= plot_bbox[3]:
                    if not ordered_pdf_points or ordered_pdf_points[-1] != point:
                        ordered_pdf_points.append(point)
        ordered_pdf_points.sort(key=lambda point: (point[0], point[1]))
        for point_index, (pdf_x, pdf_y) in enumerate(ordered_pdf_points):
            pixel_x, pixel_y = transform.pdf_to_pixel(pdf_x, pdf_y)
            calibration_points = tuple(
                [{"axis": 0.0, "coordinate": item.coordinate, "value": item.value} for item in x_calibration.anchors]
                + [{"axis": 1.0, "coordinate": item.coordinate, "value": item.value} for item in y_calibration.anchors]
            )
            points.append(FigurePoint(
                paper_id=figure.paper_id, source_asset_id=figure.source_asset_id,
                source_file_sha256=figure.source_file_sha256, figure_id=figure.figure_id,
                panel_id=figure.panel_id, page=figure.page, figure_bbox=figure.figure_bbox,
                panel_bbox=figure.panel_bbox, series_id=series_id, series_label=None,
                point_index=point_index, pixel_x=pixel_x, pixel_y=pixel_y,
                x_value=x_calibration.value(pdf_x), x_unit=None,
                y_value=y_calibration.value(pdf_y), y_unit=None,
                x_axis_scale=x_calibration.scale, y_axis_scale=y_calibration.scale,
                measurement_source_class=MeasurementSourceClass.FIGURE_VECTOR,
                extractor_name="enh3bench-pymupdf-vector", extractor_version=extractor_version,
                calibration_method="PDF_TEXT_TICKS_AND_VECTOR_AXES", calibration_points=calibration_points,
                digitization_uncertainty_x=abs(x_calibration.slope) * 0.5,
                digitization_uncertainty_y=abs(y_calibration.slope) * 0.5,
                qa_status=ExtractionStatus.REVIEW_REQUIRED,
                source_locator=f"{figure.source_asset_id}#page={figure.page}&bbox={','.join(map(str, bbox))}",
                caption=figure.caption,
            ))
    if not decline:
        decline.append("empirical benchmark acceptance gate is not established for v1")
    status = ExtractionStatus.REVIEW_REQUIRED
    manifest = ExtractionManifest(figure, "enh3bench-pymupdf-vector", extractor_version, status, decline, points)
    calibration = {
        "method": "PDF_TEXT_TICKS_AND_VECTOR_AXES", "plot_bbox": list(plot_bbox),
        "x": x_calibration.to_dict(), "y": y_calibration.to_dict(),
        "tick_text_source": "born-digital PDF text coordinates",
    }
    return manifest, calibration
