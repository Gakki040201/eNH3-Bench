from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .schema import BindingDecision, BindingMethod, FigurePoint


def separate_points_by_style(points: Iterable[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for point in points:
        style = str(point.get("style_key") or "").strip()
        if not style:
            raise ValueError("series separation requires an explicit style_key")
        groups[style].append(point)
    return {key: sorted(value, key=lambda item: (float(item["pixel_x"]), float(item["pixel_y"]))) for key, value in sorted(groups.items())}


def bind_same_paper(
    point: FigurePoint,
    *,
    experiment_paper_id: str,
    experiment_series_id: str,
    method: BindingMethod,
    evidence_locator: str,
) -> BindingDecision:
    return BindingDecision(
        figure_point_id=point.figure_point_id,
        point_paper_id=point.paper_id,
        experiment_paper_id=experiment_paper_id,
        experiment_series_id=experiment_series_id,
        method=method,
        evidence_locator=evidence_locator,
    )
