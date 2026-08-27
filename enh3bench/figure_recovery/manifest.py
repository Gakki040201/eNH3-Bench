from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import FigureContentType, FigureRecord, write_json


def write_figure_manifest(path: str | Path, records: Iterable[FigureRecord]) -> None:
    ordered = sorted(records, key=lambda item: (item.paper_id, item.source_asset_id, item.page, item.figure_label, item.panel_label or ""))
    write_json(path, {"schema_version": "figure-recovery/1.0", "figures": [item.to_dict() for item in ordered]})


def read_figure_manifest(path: str | Path) -> list[FigureRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("figures", payload if isinstance(payload, list) else [])
    result: list[FigureRecord] = []
    for item in records:
        value = dict(item)
        value["figure_content_type"] = FigureContentType(value.get("figure_content_type", "UNKNOWN"))
        for field in ("figure_bbox", "panel_bbox", "caption_bbox"):
            if value.get(field) is not None:
                value[field] = tuple(value[field])
        result.append(FigureRecord(**value))
    return result
