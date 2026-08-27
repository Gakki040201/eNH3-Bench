from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from .calibration import PdfPixelTransform
from .schema import ExtractionManifest, FigurePoint, write_json


POINT_FIELDS = [
    "figure_point_id", "paper_id", "source_asset_id", "source_file_sha256", "figure_id", "panel_id", "page",
    "series_id", "series_label", "point_index", "pixel_x", "pixel_y", "x_value", "x_unit", "y_value", "y_unit",
    "x_axis_scale", "y_axis_scale", "measurement_source_class", "extractor_name", "extractor_version",
    "calibration_method", "digitization_uncertainty_x", "digitization_uncertainty_y", "qa_status", "source_locator",
]


def create_qa_overlay(
    image_path: str | Path,
    output_path: str | Path,
    points: Iterable[FigurePoint],
    *,
    transform: PdfPixelTransform | None = None,
    axis_bbox_pdf: tuple[float, float, float, float] | None = None,
) -> Path:
    source = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(source)
    if transform is not None and axis_bbox_pdf is not None:
        left, top = transform.pdf_to_pixel(axis_bbox_pdf[0], axis_bbox_pdf[1])
        right, bottom = transform.pdf_to_pixel(axis_bbox_pdf[2], axis_bbox_pdf[3])
        draw.rectangle((left, top, right, bottom), outline=(0, 220, 255), width=max(2, source.width // 500))
    palette = [(255, 0, 255), (0, 220, 0), (255, 128, 0), (0, 128, 255), (255, 0, 0)]
    series_colors: dict[str, tuple[int, int, int]] = {}
    for point in sorted(points, key=lambda item: (item.series_id, item.point_index)):
        color = series_colors.setdefault(point.series_id, palette[len(series_colors) % len(palette)])
        radius = max(3, source.width // 400)
        draw.ellipse((point.pixel_x - radius, point.pixel_y - radius, point.pixel_x + radius, point.pixel_y + radius), outline=color, width=max(2, radius // 2))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    source.save(output)
    return output


def write_qa_bundle(
    output_dir: str | Path,
    *,
    rendered_image: str | Path,
    manifest: ExtractionManifest,
    calibration: dict[str, object],
    transform: PdfPixelTransform | None = None,
    axis_bbox_pdf: tuple[float, float, float, float] | None = None,
) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "calibration.json", calibration)
    manifest.write(root / "extraction_manifest.json")
    _write_points(root / "points.csv", manifest.points)
    create_qa_overlay(rendered_image, root / "qa_overlay.png", manifest.points, transform=transform, axis_bbox_pdf=axis_bbox_pdf)


def _write_points(path: Path, points: Iterable[FigurePoint]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=POINT_FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for point in sorted(points, key=lambda item: (item.series_id, item.point_index)):
            writer.writerow(point.to_dict())
