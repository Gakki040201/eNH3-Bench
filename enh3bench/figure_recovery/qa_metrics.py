from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left
from math import hypot
from typing import Iterable


@dataclass(frozen=True)
class BenchmarkMetrics:
    matched_points: int
    ground_truth_points: int
    extracted_points: int
    point_precision: float
    point_recall: float
    x_normalized_mae: float | None
    y_normalized_mae: float | None
    maximum_absolute_x_error: float | None
    maximum_absolute_y_error: float | None
    maximum_fe_percentage_point_error: float | None
    missing_point_rate: float
    extra_point_rate: float

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def compare_points(
    extracted: Iterable[tuple[float, float]],
    truth: Iterable[tuple[float, float]],
    *,
    x_range: float,
    y_range: float,
    tolerance_x: float,
    tolerance_y: float,
    y_is_fe_percent: bool = False,
) -> BenchmarkMetrics:
    extracted_values, truth_values = list(extracted), list(truth)
    unmatched = set(range(len(extracted_values)))
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for expected in truth_values:
        candidates = [index for index in unmatched if abs(extracted_values[index][0] - expected[0]) <= tolerance_x and abs(extracted_values[index][1] - expected[1]) <= tolerance_y]
        if not candidates:
            continue
        best = min(candidates, key=lambda index: hypot((extracted_values[index][0] - expected[0]) / max(tolerance_x, 1e-15), (extracted_values[index][1] - expected[1]) / max(tolerance_y, 1e-15)))
        unmatched.remove(best)
        pairs.append((extracted_values[best], expected))
    x_errors = [abs(left[0] - right[0]) for left, right in pairs]
    y_errors = [abs(left[1] - right[1]) for left, right in pairs]
    matched = len(pairs)
    precision = matched / len(extracted_values) if extracted_values else 0.0
    recall = matched / len(truth_values) if truth_values else 0.0
    return BenchmarkMetrics(
        matched, len(truth_values), len(extracted_values), precision, recall,
        sum(x_errors) / len(x_errors) / x_range if x_errors and x_range else None,
        sum(y_errors) / len(y_errors) / y_range if y_errors and y_range else None,
        max(x_errors) if x_errors else None, max(y_errors) if y_errors else None,
        max(y_errors) if y_is_fe_percent and y_errors else None,
        1.0 - recall, 1.0 - precision,
    )


def compare_curve(
    extracted: Iterable[tuple[float, float]],
    truth: Iterable[tuple[float, float]],
    *,
    tolerance_x: float,
    tolerance_y: float,
    y_is_fe_percent: bool = False,
) -> BenchmarkMetrics:
    """Compare dense curve vertices using source-coordinate nearest neighbors.

    Tolerances are reported inputs (normally the native half-point geometry
    uncertainty), not scientific PASS thresholds.
    """
    extracted_values = sorted(extracted)
    truth_values = sorted(truth)
    if not extracted_values or not truth_values:
        return compare_points(extracted_values, truth_values, x_range=1, y_range=1, tolerance_x=tolerance_x, tolerance_y=tolerance_y, y_is_fe_percent=y_is_fe_percent)
    truth_x = [item[0] for item in truth_values]
    extracted_x = [item[0] for item in extracted_values]
    extracted_errors = [_nearest_error(point, truth_values, truth_x) for point in extracted_values]
    truth_errors = [_nearest_error(point, extracted_values, extracted_x) for point in truth_values]
    precision = sum(dx <= tolerance_x and dy <= tolerance_y for dx, dy in extracted_errors) / len(extracted_errors)
    recall = sum(dx <= tolerance_x and dy <= tolerance_y for dx, dy in truth_errors) / len(truth_errors)
    x_errors = [item[0] for item in extracted_errors]
    y_errors = [item[1] for item in extracted_errors]
    x_range = max(truth_x) - min(truth_x)
    truth_y = [item[1] for item in truth_values]
    y_range = max(truth_y) - min(truth_y)
    return BenchmarkMetrics(
        matched_points=sum(dx <= tolerance_x and dy <= tolerance_y for dx, dy in extracted_errors),
        ground_truth_points=len(truth_values), extracted_points=len(extracted_values),
        point_precision=precision, point_recall=recall,
        x_normalized_mae=sum(x_errors) / len(x_errors) / x_range if x_range else None,
        y_normalized_mae=sum(y_errors) / len(y_errors) / y_range if y_range else None,
        maximum_absolute_x_error=max(x_errors), maximum_absolute_y_error=max(y_errors),
        maximum_fe_percentage_point_error=max(y_errors) if y_is_fe_percent else None,
        missing_point_rate=1 - recall, extra_point_rate=1 - precision,
    )


def _nearest_error(point: tuple[float, float], candidates: list[tuple[float, float]], xs: list[float]) -> tuple[float, float]:
    index = bisect_left(xs, point[0])
    choices = candidates[max(0, index - 2):min(len(candidates), index + 3)]
    nearest = min(choices, key=lambda value: abs(value[0] - point[0]))
    return abs(nearest[0] - point[0]), abs(nearest[1] - point[1])
