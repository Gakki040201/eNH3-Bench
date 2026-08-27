from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image

from enh3bench.figure_recovery.calibration import AxisCalibration, CalibrationAnchor, PdfPixelTransform
from enh3bench.figure_recovery.locator import classify_figure_content, locate_figures
from enh3bench.figure_recovery.manifest import write_figure_manifest
from enh3bench.figure_recovery.qa import create_qa_overlay
from enh3bench.figure_recovery.qa_metrics import compare_points
from enh3bench.figure_recovery.schema import (
    AxisScale,
    BindingMethod,
    ExtractionManifest,
    ExtractionStatus,
    FigureContentType,
    FigurePoint,
    FigureRecord,
    MeasurementSourceClass,
)
from enh3bench.figure_recovery.series import bind_same_paper, separate_points_by_style
from enh3bench.figure_recovery.vector_pdf import infer_calibration, inventory_paths


SHA = "a" * 64


class _Approx:
    def __init__(self, expected: object, tolerance: float = 1e-7) -> None:
        self.expected = expected
        self.tolerance = tolerance

    def __eq__(self, actual: object) -> bool:
        if isinstance(self.expected, tuple) and isinstance(actual, tuple):
            return len(self.expected) == len(actual) and all(math.isclose(float(left), float(right), rel_tol=self.tolerance, abs_tol=self.tolerance) for left, right in zip(self.expected, actual))
        return math.isclose(float(actual), float(self.expected), rel_tol=self.tolerance, abs_tol=self.tolerance)


class _Raises:
    def __init__(self, exception: type[BaseException], match: str) -> None:
        self.exception = exception
        self.match = match

    def __enter__(self) -> None:
        return None

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: object) -> bool:
        if exception_type is None:
            raise AssertionError(f"{self.exception.__name__} was not raised")
        if not issubclass(exception_type, self.exception):
            return False
        if self.match not in str(exception):
            raise AssertionError(f"{self.match!r} not found in {str(exception)!r}")
        return True


class _Assertions:
    @staticmethod
    def approx(expected: object) -> _Approx:
        return _Approx(expected)

    @staticmethod
    def raises(exception: type[BaseException], *, match: str) -> _Raises:
        return _Raises(exception, match)


pytest = _Assertions()


def _vector_pdf(path: Path, *, panels: bool = False) -> Path:
    document = fitz.open()
    page = document.new_page(width=400, height=400)
    page.draw_line((70, 250), (320, 250), color=(0, 0, 0), width=1)
    page.draw_line((70, 250), (70, 60), color=(0, 0, 0), width=1)
    page.draw_polyline([(70, 230), (150, 180), (230, 150), (320, 90)], color=(1, 0, 0), width=2)
    page.insert_text((65, 270), "0", fontsize=9)
    page.insert_text((190, 270), "5", fontsize=9)
    page.insert_text((310, 270), "10", fontsize=9)
    page.insert_text((45, 250), "0", fontsize=9)
    page.insert_text((40, 155), "50", fontsize=9)
    page.insert_text((35, 65), "100", fontsize=9)
    if panels:
        page.insert_text((20, 30), "a", fontsize=10)
        page.insert_text((210, 30), "b", fontsize=10)
    page.insert_textbox((30, 300, 370, 350), "Figure 1. A source-backed line chart.", fontsize=10)
    document.save(path)
    document.close()
    return path


def _raster_pdf(path: Path, image_path: Path) -> Path:
    Image.new("RGB", (100, 80), "white").save(image_path)
    document = fitz.open()
    page = document.new_page(width=400, height=400)
    page.insert_image((50, 50, 350, 250), filename=str(image_path))
    page.insert_textbox((30, 300, 370, 350), "Fig. S1. Raster chart.", fontsize=10)
    document.save(path)
    document.close()
    return path


def _figure(**changes: object) -> FigureRecord:
    values = dict(
        paper_id="P0015", bundle_id="B0015", source_asset_id="A-main", source_file_sha256=SHA,
        page=1, figure_label="Figure 1", caption="Figure 1. Caption", figure_bbox=(0, 0, 400, 300),
        figure_content_type=FigureContentType.VECTOR,
    )
    values.update(changes)
    return FigureRecord(**values)


def _point(**changes: object) -> FigurePoint:
    values = dict(
        paper_id="P0015", source_asset_id="A-main", source_file_sha256=SHA, figure_id="FIG-1",
        panel_id=None, page=1, figure_bbox=(0, 0, 400, 300), panel_bbox=None,
        series_id="series-001", series_label="FE", point_index=0, pixel_x=10.0, pixel_y=20.0,
        x_value=1.0, x_unit="V", y_value=50.0, y_unit="%", x_axis_scale=AxisScale.LINEAR,
        y_axis_scale=AxisScale.LINEAR, measurement_source_class=MeasurementSourceClass.FIGURE_VECTOR,
        extractor_name="test", extractor_version="1", calibration_method="PDF_TEXT_TICKS_AND_VECTOR_AXES",
        calibration_points=({"coordinate": 0.0, "value": 0.0}, {"coordinate": 1.0, "value": 1.0}),
        digitization_uncertainty_x=0.01, digitization_uncertainty_y=0.1,
        qa_status=ExtractionStatus.AUTO_PASS, source_locator="A-main#page=1", caption="Figure 1. Caption",
    )
    values.update(changes)
    return FigurePoint(**values)


def test_vector_pdf_detected_as_vector(tmp_path: Path) -> None:
    path = _vector_pdf(tmp_path / "vector.pdf")
    records = locate_figures(path, paper_id="P0015", bundle_id="B0015", source_asset_id="A")
    assert records and records[0].figure_content_type == FigureContentType.VECTOR


def test_raster_pdf_detected_as_raster(tmp_path: Path) -> None:
    path = _raster_pdf(tmp_path / "raster.pdf", tmp_path / "chart.png")
    with fitz.open(path) as document:
        assert classify_figure_content(document[0], (0, 0, 400, 300)) == FigureContentType.RASTER


def test_get_drawings_geometry_preserved(tmp_path: Path) -> None:
    path = _vector_pdf(tmp_path / "vector.pdf")
    paths = inventory_paths(path, 1, (0, 0, 400, 300))
    assert any(item.points[0] == (70.0, 250.0) and item.points[-1] == (320.0, 250.0) for item in paths)


def test_linear_calibration() -> None:
    calibration = AxisCalibration.fit([CalibrationAnchor(10, 0), CalibrationAnchor(110, 50)], AxisScale.LINEAR)
    assert calibration.value(60) == pytest.approx(25)
    assert calibration.coordinate(25) == pytest.approx(60)


def test_log_calibration() -> None:
    calibration = AxisCalibration.fit([CalibrationAnchor(10, 1), CalibrationAnchor(110, 100)], AxisScale.LOG)
    assert calibration.value(60) == pytest.approx(10)
    assert calibration.coordinate(10) == pytest.approx(60)


def test_pdf_pixel_coordinate_round_trip() -> None:
    transform = PdfPixelTransform.for_bbox((10, 20, 110, 220), 600)
    pixel = transform.pdf_to_pixel(45.5, 123.25)
    assert transform.pixel_to_pdf(*pixel) == pytest.approx((45.5, 123.25))
    assert transform.to_dict()["render_dpi"] == 600


def test_multi_series_separation() -> None:
    points = [
        {"style_key": "red", "pixel_x": 3, "pixel_y": 2},
        {"style_key": "blue", "pixel_x": 2, "pixel_y": 4},
        {"style_key": "red", "pixel_x": 1, "pixel_y": 3},
    ]
    result = separate_points_by_style(points)
    assert list(result) == ["blue", "red"]
    assert [item["pixel_x"] for item in result["red"]] == [1, 3]


def test_figure_panel_ownership_is_bundle_local(tmp_path: Path) -> None:
    path = _vector_pdf(tmp_path / "panels.pdf", panels=True)
    records = locate_figures(path, paper_id="P0015", bundle_id="B0015", source_asset_id="A")
    assert records
    assert {item.paper_id for item in records} == {"P0015"}
    assert {item.bundle_id for item in records} == {"B0015"}
    assert all(item.figure_id.startswith("FIG_") for item in records)


def test_same_paper_binding_only() -> None:
    point = _point()
    decision = bind_same_paper(point, experiment_paper_id="P0015", experiment_series_id="E1", method=BindingMethod.SAME_FIGURE_SERIES, evidence_locator="caption")
    assert decision.experiment_series_id == "E1"


def test_no_cross_paper_inheritance() -> None:
    with pytest.raises(ValueError, match="cross-paper"):
        bind_same_paper(_point(), experiment_paper_id="P0016", experiment_series_id="E1", method=BindingMethod.DETERMINISTIC_SAME_PAPER_INHERITANCE, evidence_locator="methods")


def test_source_data_benchmark_comparison() -> None:
    metrics = compare_points([(0.0, 50.2), (1.0, 74.8)], [(0.0, 50.0), (1.0, 75.0)], x_range=1, y_range=100, tolerance_x=0.01, tolerance_y=0.5, y_is_fe_percent=True)
    assert metrics.point_precision == 1
    assert metrics.point_recall == 1
    assert metrics.maximum_fe_percentage_point_error == pytest.approx(0.2)


def test_qa_overlay_generation(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "qa_overlay.png"
    Image.new("RGB", (200, 100), "white").save(source)
    create_qa_overlay(source, output, [_point(pixel_x=50, pixel_y=40)])
    assert output.is_file()
    assert Image.open(output).getpixel((50, 37)) != (255, 255, 255)


def test_fail_closed_ambiguous_axis() -> None:
    with pytest.raises(ValueError, match="ambiguous axis scale"):
        infer_calibration([CalibrationAnchor(0, 1), CalibrationAnchor(100, 10)])


def test_deterministic_extraction_manifest(tmp_path: Path) -> None:
    figure = _figure()
    manifest = ExtractionManifest(figure, "test", "1", ExtractionStatus.AUTO_PASS, points=[_point(figure_id=figure.figure_id)])
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    manifest.write(left)
    manifest.write(right)
    assert left.read_bytes() == right.read_bytes()
    assert json.loads(left.read_text(encoding="utf-8"))["schema_version"] == "figure-recovery/1.0"


def test_deterministic_figure_manifest(tmp_path: Path) -> None:
    records = [_figure(figure_label="Figure 2"), _figure(figure_label="Figure 1")]
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    write_figure_manifest(left, records)
    write_figure_manifest(right, reversed(records))
    assert left.read_bytes() == right.read_bytes()


class FigureRecoveryV1Test(unittest.TestCase):
    def _tmp(self, function: object) -> None:
        with tempfile.TemporaryDirectory() as directory:
            function(Path(directory))  # type: ignore[operator]

    def test_vector_pdf_detected_as_vector(self) -> None:
        self._tmp(test_vector_pdf_detected_as_vector)

    def test_raster_pdf_detected_as_raster(self) -> None:
        self._tmp(test_raster_pdf_detected_as_raster)

    def test_get_drawings_geometry_preserved(self) -> None:
        self._tmp(test_get_drawings_geometry_preserved)

    def test_linear_calibration(self) -> None:
        test_linear_calibration()

    def test_log_calibration(self) -> None:
        test_log_calibration()

    def test_pdf_pixel_coordinate_round_trip(self) -> None:
        test_pdf_pixel_coordinate_round_trip()

    def test_multi_series_separation(self) -> None:
        test_multi_series_separation()

    def test_figure_panel_ownership_is_bundle_local(self) -> None:
        self._tmp(test_figure_panel_ownership_is_bundle_local)

    def test_same_paper_binding_only(self) -> None:
        test_same_paper_binding_only()

    def test_no_cross_paper_inheritance(self) -> None:
        test_no_cross_paper_inheritance()

    def test_source_data_benchmark_comparison(self) -> None:
        test_source_data_benchmark_comparison()

    def test_qa_overlay_generation(self) -> None:
        self._tmp(test_qa_overlay_generation)

    def test_fail_closed_ambiguous_axis(self) -> None:
        test_fail_closed_ambiguous_axis()

    def test_deterministic_extraction_manifest(self) -> None:
        self._tmp(test_deterministic_extraction_manifest)

    def test_deterministic_figure_manifest(self) -> None:
        self._tmp(test_deterministic_figure_manifest)
