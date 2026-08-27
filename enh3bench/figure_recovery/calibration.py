from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .schema import AxisScale, BBox


@dataclass(frozen=True)
class CalibrationAnchor:
    coordinate: float
    value: float


@dataclass(frozen=True)
class AxisCalibration:
    scale: AxisScale
    slope: float
    intercept: float
    anchors: tuple[CalibrationAnchor, ...]
    rms_residual: float

    @classmethod
    def fit(cls, anchors: Iterable[CalibrationAnchor], scale: AxisScale = AxisScale.LINEAR) -> "AxisCalibration":
        points = tuple(anchors)
        if len(points) < 2:
            raise ValueError("at least two calibration anchors are required")
        if len({round(point.coordinate, 12) for point in points}) < 2:
            raise ValueError("calibration coordinates are ambiguous")
        transformed: list[tuple[float, float]] = []
        for point in points:
            if scale == AxisScale.LOG and point.value <= 0:
                raise ValueError("log calibration values must be positive")
            transformed.append((point.coordinate, math.log10(point.value) if scale == AxisScale.LOG else point.value))
        xs = [point[0] for point in transformed]
        ys = [point[1] for point in transformed]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        denominator = sum((value - mean_x) ** 2 for value in xs)
        if denominator == 0:
            raise ValueError("calibration coordinates are ambiguous")
        slope = sum((x - mean_x) * (y - mean_y) for x, y in transformed) / denominator
        intercept = mean_y - slope * mean_x
        residual = math.sqrt(sum((slope * x + intercept - y) ** 2 for x, y in transformed) / len(transformed))
        return cls(scale=scale, slope=slope, intercept=intercept, anchors=points, rms_residual=residual)

    def value(self, coordinate: float) -> float:
        transformed = self.slope * float(coordinate) + self.intercept
        return 10**transformed if self.scale == AxisScale.LOG else transformed

    def coordinate(self, value: float) -> float:
        if self.scale == AxisScale.LOG:
            if value <= 0:
                raise ValueError("log values must be positive")
            value = math.log10(value)
        if self.slope == 0:
            raise ValueError("zero-slope calibration")
        return (float(value) - self.intercept) / self.slope

    def to_dict(self) -> dict[str, object]:
        return {
            "scale": self.scale.value,
            "slope": self.slope,
            "intercept": self.intercept,
            "rms_residual": self.rms_residual,
            "anchors": [{"coordinate": item.coordinate, "value": item.value} for item in self.anchors],
        }


@dataclass(frozen=True)
class PdfPixelTransform:
    bbox: BBox
    dpi: int
    pixel_width: int
    pixel_height: int

    @classmethod
    def for_bbox(cls, bbox: BBox, dpi: int, pixel_width: int | None = None, pixel_height: int | None = None) -> "PdfPixelTransform":
        if dpi <= 0:
            raise ValueError("dpi must be positive")
        scale = dpi / 72.0
        width = pixel_width if pixel_width is not None else round((bbox[2] - bbox[0]) * scale)
        height = pixel_height if pixel_height is not None else round((bbox[3] - bbox[1]) * scale)
        if width <= 0 or height <= 0:
            raise ValueError("invalid rendered dimensions")
        return cls(bbox=bbox, dpi=dpi, pixel_width=width, pixel_height=height)

    @property
    def scale_x(self) -> float:
        return self.pixel_width / (self.bbox[2] - self.bbox[0])

    @property
    def scale_y(self) -> float:
        return self.pixel_height / (self.bbox[3] - self.bbox[1])

    def pdf_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.bbox[0]) * self.scale_x, (y - self.bbox[1]) * self.scale_y)

    def pixel_to_pdf(self, x: float, y: float) -> tuple[float, float]:
        return (self.bbox[0] + x / self.scale_x, self.bbox[1] + y / self.scale_y)

    def matrix(self) -> list[list[float]]:
        return [[self.scale_x, 0.0, -self.bbox[0] * self.scale_x], [0.0, self.scale_y, -self.bbox[1] * self.scale_y], [0.0, 0.0, 1.0]]

    def to_dict(self) -> dict[str, object]:
        return {"pdf_bbox": list(self.bbox), "render_dpi": self.dpi, "pixel_dimensions": [self.pixel_width, self.pixel_height], "transformation_matrix": self.matrix()}
