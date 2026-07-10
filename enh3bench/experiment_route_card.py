"""Markdown route cards for lab-constrained experiment plans."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from enh3bench.ledger_router import load_jsonl


def route_to_markdown_card(route: dict[str, Any], index: int | None = None) -> str:
    """Render one structured route card as Markdown."""

    prefix = f"{index}. " if index is not None else ""
    lines = [
        f"# {prefix}{route.get('route_id', 'route')}: {route.get('route_type', '')}",
        "",
        "## 1. Recommendation / 建议",
        "",
        f"Priority: `{route.get('priority_label')}` (score {route.get('priority_score')}).",
        f"Reaction family: `{route.get('reaction_family') or 'unclear'}`.",
        f"Lab demonstration allowed: `{bool(route.get('lab_demonstration_allowed'))}`.",
        f"Reaction profile: {_reaction_profile_line(route.get('reaction_profile'))}",
        "",
        "## 2. Hypothesis / 假设",
        "",
        str(route.get("hypothesis") or ""),
        "",
        "## 3. Why Recommended / 推荐理由",
        "",
        str(route.get("literature_rationale") or ""),
        "",
        "## 4. Literature Boundary Gap / 文献边界缺口",
        "",
        _bullet_list(route.get("boundary_gap_targeted")),
        "",
        "## 5. Hidden Tax Tested / 隐性代价",
        "",
        _bullet_list(route.get("hidden_tax_targeted")),
        "",
        "## 6. Lab Feasibility / 实验室可行性",
        "",
        f"- Feasible controls: {', '.join(_list_values(route.get('feasible_controls'))) or 'none'}",
        f"- Infeasible controls: {', '.join(_list_values(route.get('infeasible_controls'))) or 'none'}",
        f"- Capability warnings: {', '.join(_list_values(route.get('lab_capability_warnings'))) or 'none'}",
        "",
        "## 7. Experimental Matrix / 实验矩阵",
        "",
        _json_block(route.get("experimental_matrix")),
        "",
        "## 8. Required Controls / 必需对照",
        "",
        _bullet_list(route.get("required_controls")),
        "",
        "## 9. Required Measurements / 必需测量",
        "",
        _bullet_list(route.get("required_measurements")),
        "",
        "## 10. Success Criteria / 成功标准",
        "",
        _bullet_list(route.get("success_criteria")),
        "",
        "## 11. Failure Criteria / 失败标准",
        "",
        _bullet_list(route.get("failure_criteria")),
        "",
        "## 12. Failure Diagnosis Tree / 失败诊断树",
        "",
        _bullet_list(route.get("failure_diagnosis_tree")),
        "",
        "## 13. Claim Support If Successful / 成功后可支持的声明",
        "",
        "A successful route can support only the targeted measured boundary fields and controls recorded in the route result.",
        "",
        "## 14. Claim Still Not Supported / 仍不能支持的声明",
        "",
        "The route cannot support plant-facing or generalized literature claims unless process closure and mandatory controls are explicitly measured.",
        "",
        "## 15. Human Review Flags / 人工审核标记",
        "",
        f"- Human review required: {bool(route.get('human_review_required'))}",
        f"- LLM used: {bool(route.get('llm_used'))}",
        f"- LLM rationale: {route.get('llm_rationale') or ''}",
        "",
    ]
    return "\n".join(lines)


def export_route_cards(
    routes: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/experiment_routes",
) -> str:
    """Export all route cards into one Markdown file."""

    output_path = Path(output_dir) / run_name / "route_cards.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n\n---\n\n".join(route_to_markdown_card(route, index + 1) for index, route in enumerate(routes))
    output_path.write_text(text or "# Experiment Route Cards\n\nNo routes generated.\n", encoding="utf-8", newline="\n")
    return str(output_path)


def export_public_route_summary(
    routes: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/reports",
) -> str:
    """Export a concise public route-planning summary."""

    output_path = Path(output_dir) / f"experiment_route_summary.{run_name}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    priority_counts = Counter(str(route.get("priority_label") or "missing") for route in routes)
    route_type_counts = Counter(str(route.get("route_type") or "missing") for route in routes)
    family_counts = Counter(str(route.get("reaction_family") or "unclear") for route in routes)
    lines = [
        f"# Experiment Route Summary: {run_name}",
        "",
        "## 1. Route counts",
        "",
        f"- Routes generated: {len(routes)}",
        "",
        "## 2. Priority labels",
        "",
        _table(["Priority", "Routes"], priority_counts.items()),
        "",
        "## 3. Route types",
        "",
        _table(["Route type", "Routes"], route_type_counts.items()),
        "",
        "## 4. Reaction families",
        "",
        _table(["Reaction family", "Routes"], family_counts.items()),
        "",
        "## 5. Safety statement",
        "",
        "These route cards are structured planning artifacts, not wet-lab SOPs. Local safety review and human scientific review remain mandatory.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(output_path)


def load_ranked_routes(run_name: str, base_dir: str | Path = "data/experiment_routes") -> list[dict[str, Any]]:
    return load_jsonl(Path(base_dir) / run_name / "ranked_experiment_routes.jsonl")


def _reaction_profile_line(value: Any) -> str:
    if not isinstance(value, dict):
        return "none"
    family = str(value.get("reaction_family") or "unclear")
    nitrogen_source = str(value.get("nitrogen_source") or "unknown nitrogen source")
    allowed = bool(value.get("experimental_demonstration_allowed"))
    return f"{family}; nitrogen_source={nitrogen_source}; lab_demo_default={allowed}"


def _bullet_list(value: Any) -> str:
    items = _list_values(value)
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=True, sort_keys=True)] if value else []
    text = str(value).strip()
    return [text] if text else []


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value or [], ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n```"


def _table(headers: list[str], rows: Any) -> str:
    rows = list(rows)
    if not rows:
        return "No records."
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for key, count in sorted(rows, key=lambda item: (-item[1], item[0])):
        safe_key = str(key).replace("|", "\\|")
        lines.append(f"| {safe_key} | {count} |")
    return "\n".join(lines)
