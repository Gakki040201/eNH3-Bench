from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.figure_recovery.locator import locate_figures  # noqa: E402
from enh3bench.figure_recovery.manifest import write_figure_manifest  # noqa: E402
from enh3bench.figure_recovery.qa import write_qa_bundle  # noqa: E402
from enh3bench.figure_recovery.raster import availability_report, render_bbox  # noqa: E402
from enh3bench.figure_recovery.schema import ExtractionManifest, ExtractionStatus, FigureContentType, write_json  # noqa: E402
from enh3bench.figure_recovery.vector_pdf import inventory_figure, recover_vector_points  # noqa: E402


DEFAULT_OUTPUT = Path(r"F:\eNH3_Bench_Work\02_Data\Figure_Recovery\LiNRR_Figure_Recovery_v1")
DEFAULT_THIRD_PARTY = Path(r"F:\eNH3_Bench_Work\99_Scratch\Figure_Recovery_ThirdParty")
MAX_PILOT_FIGURES = 40


def load_assets(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assets = payload.get("assets", payload if isinstance(payload, list) else [])
    required = {"paper_id", "bundle_id", "source_asset_id", "pdf_path"}
    result = []
    for value in assets:
        row = {key: str(item) for key, item in value.items()}
        missing = sorted(required - row.keys())
        if missing:
            raise ValueError(f"asset missing fields {missing}")
        if Path(row["pdf_path"]).suffix.lower() != ".pdf":
            raise ValueError("only local PDF assets are accepted")
        result.append(row)
    return result


def run(
    asset_index: Path,
    output_root: Path,
    *,
    limit: int,
    dpis: tuple[int, ...],
    third_party_root: Path,
    include_labels: set[str] | None = None,
) -> dict[str, object]:
    if limit < 1 or limit > MAX_PILOT_FIGURES:
        raise ValueError(f"pilot limit must be between 1 and {MAX_PILOT_FIGURES}")
    assets = load_assets(asset_index)
    figures = []
    asset_paths: dict[str, Path] = {}
    for asset in assets:
        pdf_path = Path(asset["pdf_path"])
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        asset_paths[asset["source_asset_id"]] = pdf_path
        figures.extend(locate_figures(pdf_path, paper_id=asset["paper_id"], bundle_id=asset["bundle_id"], source_asset_id=asset["source_asset_id"]))
    figures = sorted(figures, key=lambda item: (item.paper_id, item.source_asset_id, item.page, item.figure_label, item.panel_label or ""))
    if include_labels is not None:
        figures = [item for item in figures if item.figure_label in include_labels]
        missing = sorted(include_labels - {item.figure_label for item in figures})
        if missing:
            raise ValueError(f"selected benchmark figure labels were not located: {missing}")
    figures = figures[:limit]
    output_root.mkdir(parents=True, exist_ok=True)
    write_figure_manifest(output_root / "figure_manifest.json", figures)
    write_json(output_root / "extractor_availability.json", availability_report(third_party_root))
    results = []
    for figure in figures:
        pdf_path = asset_paths[figure.source_asset_id]
        figure_root = output_root / figure.paper_id / figure.figure_id / (figure.panel_id or "whole-figure")
        bbox = figure.panel_bbox or figure.figure_bbox
        rendered = {}
        for dpi in dpis:
            render = render_bbox(pdf_path, figure.page, bbox, figure_root / f"render_{dpi}dpi.png", dpi=dpi)
            rendered[str(dpi)] = render.transform.to_dict()
        qa_render = render_bbox(pdf_path, figure.page, bbox, figure_root / "render_for_qa.png", dpi=max(dpis))
        if figure.figure_content_type in {FigureContentType.VECTOR, FigureContentType.MIXED}:
            manifest, calibration = recover_vector_points(pdf_path, figure, transform=qa_render.transform, extractor_version=_pymupdf_version())
            inventory = inventory_figure(pdf_path, figure)
            write_json(figure_root / "vector_inventory.json", inventory)
            manifest.cross_checks.append(_pdf_mcp_cross_check(pdf_path, figure.page, figure_root, third_party_root, manifest))
        elif figure.figure_content_type == FigureContentType.RASTER:
            manifest = ExtractionManifest(figure, "raster-adapter", "1.0.0", ExtractionStatus.FAILED_UNSUPPORTED, ["isolated raster model adapter unavailable or not configured"], render=rendered)
            calibration = {"method": None, "decline_reason": "axis calibration requires local OCR/model adapter or manual review"}
        else:
            manifest = ExtractionManifest(figure, "enh3bench-locator", "1.0.0", ExtractionStatus.FAILED_UNSUPPORTED, ["no vector or raster figure content detected"], render=rendered)
            calibration = {"method": None, "decline_reason": "unsupported content"}
        manifest.render = rendered
        write_qa_bundle(figure_root, rendered_image=qa_render.path, manifest=manifest, calibration=calibration, transform=qa_render.transform, axis_bbox_pdf=tuple(calibration["plot_bbox"]) if calibration.get("plot_bbox") else None)
        results.append({"figure_id": figure.figure_id, "panel_id": figure.panel_id, "status": manifest.status.value, "path": str(figure_root), "points": len(manifest.points)})
    summary = {
        "milestone": "LiNRR Figure Data Recovery v1", "pilot_only": True,
        "figure_count": len(figures), "results": results,
        "status_counts": {status: sum(1 for item in results if item["status"] == status) for status in ("AUTO_PASS", "REVIEW_REQUIRED", "FAILED_UNSUPPORTED")},
        "output_root": str(output_root),
    }
    write_json(output_root / "pilot_summary.json", summary)
    return summary


def _pymupdf_version() -> str:
    import fitz
    return str(fitz.VersionBind)


def _pdf_mcp_cross_check(pdf_path: Path, page: int, output_root: Path, third_party_root: Path, native_manifest: ExtractionManifest) -> dict[str, object | None]:
    repo = third_party_root / "pdf-mcp"
    adapter = ROOT / "scripts" / "figure_recovery_pdf_mcp_adapter.py"
    output = output_root / "pdf_mcp_result.json"
    if not (repo / "src" / "pdf_mcp" / "chart_extractor.py").is_file():
        return {"extractor": "pdf-mcp/pdf_extract_chart", "version": None, "result": "DECLINED", "decline_reason": "local pdf-mcp checkout unavailable", "agreement_with_native": None}
    completed = subprocess.run(
        [sys.executable, str(adapter), "--repo", str(repo), "--pdf", str(pdf_path), "--page", str(page), "--output", str(output)],
        capture_output=True, text=True, check=False, timeout=180,
    )
    if completed.returncode != 0 or not output.is_file():
        reason = (completed.stderr or completed.stdout or f"exit {completed.returncode}").strip()[-1000:]
        return {"extractor": "pdf-mcp/pdf_extract_chart", "version": None, "result": "DECLINED", "decline_reason": reason, "agreement_with_native": None}
    payload = json.loads(output.read_text(encoding="utf-8"))
    external_points = payload.get("point_count", 0)
    agreement = None
    if native_manifest.points and external_points:
        agreement = min(len(native_manifest.points), int(external_points)) / max(len(native_manifest.points), int(external_points))
    return {
        "extractor": "pdf-mcp/pdf_extract_chart", "version": payload.get("version"),
        "result": payload.get("result"), "decline_reason": payload.get("decline_reason"),
        "agreement_with_native": agreement,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local-only LiNRR figure recovery v1 pilot.")
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--third-party-root", type=Path, default=DEFAULT_THIRD_PARTY)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dpi", type=int, action="append", choices=(400, 600), dest="dpis")
    parser.add_argument("--benchmark-manifest", type=Path, help="Restrict recovery to exact figure labels in a v1 benchmark manifest.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    include_labels = None
    if args.benchmark_manifest is not None:
        benchmark = json.loads(args.benchmark_manifest.read_text(encoding="utf-8"))
        include_labels = {str(item["figure_label"]) for item in benchmark.get("benchmark_figures", [])}
        if not include_labels:
            raise ValueError("benchmark manifest contains no figure labels")
    summary = run(
        args.asset_index, args.output_root, limit=args.limit,
        dpis=tuple(sorted(set(args.dpis or [400, 600]))),
        third_party_root=args.third_party_root, include_labels=include_labels,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
