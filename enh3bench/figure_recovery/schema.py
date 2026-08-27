from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "figure-recovery/1.0"


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class FigureContentType(StringEnum):
    VECTOR = "VECTOR"
    RASTER = "RASTER"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class AxisScale(StringEnum):
    LINEAR = "LINEAR"
    LOG = "LOG"


class MeasurementSourceClass(StringEnum):
    SOURCE_DATA = "SOURCE_DATA"
    STRUCTURED_TABLE = "STRUCTURED_TABLE"
    TEXT_EXPLICIT = "TEXT_EXPLICIT"
    FIGURE_VECTOR = "FIGURE_VECTOR"
    FIGURE_RASTER = "FIGURE_RASTER"


class ExtractionStatus(StringEnum):
    AUTO_PASS = "AUTO_PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED_UNSUPPORTED = "FAILED_UNSUPPORTED"


class CandidateStatus(StringEnum):
    FIGURE_POINT_CANDIDATE = "FIGURE_POINT_CANDIDATE"


class BindingMethod(StringEnum):
    SAME_FIGURE_SERIES = "SAME_FIGURE_SERIES"
    SAME_CAPTION_DEFINED_SERIES = "SAME_CAPTION_DEFINED_SERIES"
    SAME_METHOD_DEFINED_SERIES = "SAME_METHOD_DEFINED_SERIES"
    DETERMINISTIC_SAME_PAPER_INHERITANCE = "DETERMINISTIC_SAME_PAPER_INHERITANCE"


BBox = tuple[float, float, float, float]


def normalize_bbox(value: Iterable[float]) -> BBox:
    result = tuple(round(float(item), 6) for item in value)
    if len(result) != 4 or result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError(f"invalid bbox: {result}")
    return result  # type: ignore[return-value]


def stable_id(prefix: str, *parts: object) -> str:
    canonical = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True)
class FigureRecord:
    paper_id: str
    bundle_id: str
    source_asset_id: str
    source_file_sha256: str
    page: int
    figure_label: str
    caption: str
    figure_bbox: BBox
    panel_label: str | None = None
    panel_bbox: BBox | None = None
    figure_content_type: FigureContentType = FigureContentType.UNKNOWN
    caption_bbox: BBox | None = None
    figure_id: str = ""
    panel_id: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.paper_id or not self.bundle_id or not self.source_asset_id:
            raise ValueError("paper_id, bundle_id, and source_asset_id are required")
        if self.page < 1:
            raise ValueError("page is one-based")
        if len(self.source_file_sha256) != 64:
            raise ValueError("source_file_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "figure_bbox", normalize_bbox(self.figure_bbox))
        if self.caption_bbox is not None:
            object.__setattr__(self, "caption_bbox", normalize_bbox(self.caption_bbox))
        if self.panel_bbox is not None:
            object.__setattr__(self, "panel_bbox", normalize_bbox(self.panel_bbox))
        if not self.figure_id:
            object.__setattr__(
                self,
                "figure_id",
                stable_id("FIG", self.paper_id, self.source_asset_id, self.page, self.figure_label, self.figure_bbox),
            )
        if self.panel_label and not self.panel_id:
            object.__setattr__(self, "panel_id", stable_id("PAN", self.figure_id, self.panel_label, self.panel_bbox))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True)
class FigurePoint:
    paper_id: str
    source_asset_id: str
    source_file_sha256: str
    figure_id: str
    panel_id: str | None
    page: int
    figure_bbox: BBox
    panel_bbox: BBox | None
    series_id: str
    series_label: str | None
    point_index: int
    pixel_x: float
    pixel_y: float
    x_value: float
    x_unit: str | None
    y_value: float
    y_unit: str | None
    x_axis_scale: AxisScale
    y_axis_scale: AxisScale
    measurement_source_class: MeasurementSourceClass
    extractor_name: str
    extractor_version: str
    calibration_method: str
    calibration_points: tuple[dict[str, float], ...]
    digitization_uncertainty_x: float | None
    digitization_uncertainty_y: float | None
    qa_status: ExtractionStatus
    source_locator: str
    caption: str
    figure_point_id: str = ""
    candidate_status: CandidateStatus = CandidateStatus.FIGURE_POINT_CANDIDATE
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.page < 1 or self.point_index < 0:
            raise ValueError("invalid page or point index")
        if self.measurement_source_class not in {
            MeasurementSourceClass.SOURCE_DATA,
            MeasurementSourceClass.STRUCTURED_TABLE,
            MeasurementSourceClass.TEXT_EXPLICIT,
            MeasurementSourceClass.FIGURE_VECTOR,
            MeasurementSourceClass.FIGURE_RASTER,
        }:
            raise ValueError("unsupported measurement source class")
        object.__setattr__(self, "figure_bbox", normalize_bbox(self.figure_bbox))
        if self.panel_bbox is not None:
            object.__setattr__(self, "panel_bbox", normalize_bbox(self.panel_bbox))
        if not self.figure_point_id:
            object.__setattr__(
                self,
                "figure_point_id",
                stable_id("FPT", self.paper_id, self.figure_id, self.panel_id or "", self.series_id, self.point_index),
            )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True)
class BindingDecision:
    figure_point_id: str
    point_paper_id: str
    experiment_paper_id: str
    experiment_series_id: str
    method: BindingMethod
    evidence_locator: str

    def __post_init__(self) -> None:
        if self.point_paper_id != self.experiment_paper_id:
            raise ValueError("cross-paper figure-point inheritance is forbidden")
        if not self.evidence_locator:
            raise ValueError("binding requires an evidence locator")


@dataclass
class ExtractionManifest:
    figure: FigureRecord
    extractor: str
    extractor_version: str
    status: ExtractionStatus
    decline_reasons: list[str] = field(default_factory=list)
    points: list[FigurePoint] = field(default_factory=list)
    cross_checks: list[dict[str, Any]] = field(default_factory=list)
    render: dict[str, Any] | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def write(self, path: str | Path) -> None:
        write_json(path, self.to_dict())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def write_json(path: str | Path, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
