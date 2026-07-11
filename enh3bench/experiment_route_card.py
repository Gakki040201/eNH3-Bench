"""Markdown route cards for lab-constrained experiment plans."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from enh3bench.ledger_router import load_jsonl
from enh3bench.experiment_schema import EXECUTION_STAGES, ROUTE_STAGE_MAP


def route_to_markdown_card(route: dict[str, Any], index: int | None = None) -> str:
    """Render one structured route card as Markdown."""

    prefix = f"{index}. " if index is not None else ""
    lines = [
        f"# {prefix}{route.get('route_id', 'route')}: {route.get('route_type', '')}",
        "",
        "## 1. Recommendation / 建议",
        "",
        f"Priority: `{route.get('priority_label')}` (score {route.get('priority_score')}).",
        f"Schema version: `{route.get('schema_version') or 'legacy'}`.",
        f"Migration warnings: {', '.join(_list_values(route.get('migration_warnings'))) or 'none'}",
        f"Reaction family: `{route.get('reaction_family') or 'unclear'}`.",
        f"Lab demonstration allowed: `{bool(route.get('lab_demonstration_allowed'))}`.",
        f"Reaction profile: {_reaction_profile_line(route.get('reaction_profile'))}",
        f"Execution stage: `{route.get('stage_rank', '')} {route.get('execution_stage') or ''}`.",
        f"Stage gate: `{route.get('stage_gate_status') or 'unknown'}`.",
        f"Execution order reason: {route.get('execution_order_reason') or ''}",
        f"Prerequisites: {', '.join(_list_values(route.get('prerequisite_route_ids'))) or 'none'}",
        f"Blocked by: {', '.join(_list_values(route.get('blocked_by_route_ids'))) or 'none'}",
        f"Route family: `{route.get('route_family_id') or route.get('route_type') or ''}`.",
        f"Parent route: {route.get('parent_route_id') or 'none'}",
        f"Child routes: {', '.join(_list_values(route.get('child_route_ids'))) or 'none'}",
        f"Non-executable parent: `{bool(route.get('is_route_group'))}`.",
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
        f"- Measurement feasibility: {route.get('measurement_feasibility_status') or 'unknown'}",
        f"- Feasible measurements: {', '.join(_list_values(route.get('feasible_measurements'))) or 'none'}",
        f"- Infeasible measurements: {', '.join(_list_values(route.get('infeasible_measurements'))) or 'none'}",
        f"- Measurement capability warnings: {', '.join(_list_values(route.get('measurement_capability_warnings'))) or 'none'}",
        f"- Capability warnings: {', '.join(_list_values(route.get('lab_capability_warnings'))) or 'none'}",
        f"- Alternative measurement plan: {', '.join(_list_values(route.get('alternative_measurement_plan'))) or 'none'}",
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
        "Mandatory measurements:",
        _bullet_list(route.get("mandatory_measurements")),
        "",
        "Optional measurements:",
        _bullet_list(route.get("optional_measurements")),
        "",
        "## 10. SOP Anchor Points / SOP 锚点",
        "",
        _bullet_list(route.get("SOP_anchor_points")),
        "",
        "## 11. Minimum Report Fields / 最低报告字段",
        "",
        _bullet_list(route.get("minimum_report_fields")),
        "",
        "## 12. Boundary Upgrade If Successful / 成功后可升级边界",
        "",
        _bullet_list(route.get("boundary_upgrade_if_successful")),
        "",
        "## 13. Boundary Still Not Closed / 仍未闭合边界",
        "",
        _bullet_list(route.get("boundary_not_closed_even_if_successful")),
        "",
        "Unavailable-measurement boundaries:",
        _bullet_list(route.get("boundary_not_closed_due_to_unavailable_measurements")),
        "",
        "## 14. Required Raw Records To Save / 需保存原始记录",
        "",
        _bullet_list(route.get("required_raw_records_to_save")),
        "",
        "## 15. Success Criteria / 成功标准",
        "",
        _bullet_list(route.get("success_criteria")),
        "",
        "## 16. Failure Criteria / 失败标准",
        "",
        _bullet_list(route.get("failure_criteria")),
        "",
        "## 17. Failure Diagnosis Tree / 失败诊断树",
        "",
        _bullet_list(route.get("failure_diagnosis_tree")),
        "",
        "## 18. Claim Support If Successful / 成功后可支持的声明",
        "",
        "A successful route can support only the targeted measured boundary fields and controls recorded in the route result.",
        "",
        "## 19. Claim Still Not Supported / 仍不能支持的声明",
        "",
        "The route cannot support plant-facing or generalized literature claims unless process closure and mandatory controls are explicitly measured.",
        "",
        "## 20. Human Review Flags / 人工审核标记",
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
    next_route = _next_actionable(routes)
    sections = [
        "# Experiment Route Cards",
        "",
        f"Next actionable route: `{next_route.get('route_id') if next_route else 'none'}`.",
        "",
        "## Parent-child route tree",
        "",
        _route_tree(routes),
    ]
    card_index = 1
    for stage_rank, stage_name in enumerate(EXECUTION_STAGES):
        stage_routes = [route for route in routes if _stage_rank(route) == stage_rank]
        if not stage_routes:
            continue
        sections.extend(["", f"## Stage {stage_rank}: {stage_name}", ""])
        for route in _stage_card_order(stage_routes):
            sections.extend([route_to_markdown_card(route, card_index), "", "---", ""])
            card_index += 1
    text = "\n".join(sections).rstrip() + "\n"
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
    measurement_counts = Counter(str(route.get("measurement_feasibility_status") or "unknown") for route in routes)
    stage_counts = Counter(f"{_stage_rank(route)} {route.get('execution_stage') or ''}" for route in routes)
    next_route = _next_actionable(routes)
    lines = [
        f"# Experiment Route Summary: {run_name}",
        "",
        "## 1. Route counts",
        "",
        f"- Routes generated: {len(routes)}",
        f"- Records with migration warnings: {sum(1 for route in routes if route.get('migration_warnings'))}",
        f"- Next actionable route: {next_route.get('route_id') if next_route else 'none'}",
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
        "## 5. Measurement feasibility",
        "",
        _table(["Status", "Routes"], measurement_counts.items()),
        "",
        _route_feasibility_table(routes),
        "",
        "## 6. Execution stages",
        "",
        _table(["Stage", "Routes"], stage_counts.items()),
        "",
        _route_tree(routes),
        "",
        "## 7. Safety statement",
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


def _route_feasibility_table(routes: list[dict[str, Any]]) -> str:
    if not routes:
        return "No records."
    headers = [
        "Route",
        "Feasible controls",
        "Infeasible controls",
        "Feasible measurements",
        "Infeasible measurements",
        "Alternative plan",
        "Boundary not closed",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for route in routes:
        values = [
            route.get("route_id") or "",
            ", ".join(_list_values(route.get("feasible_controls"))) or "none",
            ", ".join(_list_values(route.get("infeasible_controls"))) or "none",
            ", ".join(_list_values(route.get("feasible_measurements"))) or "none",
            ", ".join(_list_values(route.get("infeasible_measurements"))) or "none",
            ", ".join(_list_values(route.get("alternative_measurement_plan"))) or "none",
            ", ".join(_list_values(route.get("boundary_not_closed_due_to_unavailable_measurements"))) or "none",
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    return "\n".join(lines)


def _route_tree(routes: list[dict[str, Any]]) -> str:
    parents = [route for route in routes if route.get("is_route_group")]
    lines: list[str] = []
    for parent in sorted(parents, key=_card_sort_key):
        lines.append(
            f"- {parent.get('route_id')} [non-executable parent; {parent.get('stage_gate_status') or 'unknown'}]"
        )
        child_ids = set(_list_values(parent.get("child_route_ids")))
        children = [route for route in routes if str(route.get("route_id") or "") in child_ids]
        for child in sorted(children, key=_card_sort_key):
            blockers = ", ".join(_list_values(child.get("blocked_by_route_ids"))) or "none"
            lines.append(
                f"  - {child.get('route_id')} [{child.get('stage_gate_status') or 'unknown'}; blocked_by={blockers}]"
            )
    if not lines:
        return "- none"
    return "\n".join(lines)


def _next_actionable(routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            route
            for route in sorted(routes, key=_card_sort_key)
            if not route.get("is_route_group")
            and str(route.get("stage_gate_status") or "") in {"actionable", "event_triggered", "waived"}
        ),
        None,
    )


def _stage_card_order(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parents = [route for route in routes if route.get("is_route_group")]
    ordered: list[dict[str, Any]] = []
    for parent in sorted(parents, key=_card_sort_key):
        ordered.append(parent)
        child_ids = set(_list_values(parent.get("child_route_ids")))
        ordered.extend(sorted((route for route in routes if str(route.get("route_id") or "") in child_ids), key=_card_sort_key))
    included = {str(route.get("route_id") or "") for route in ordered}
    ordered.extend(sorted((route for route in routes if str(route.get("route_id") or "") not in included), key=_card_sort_key))
    return ordered


def _stage_rank(route: dict[str, Any]) -> int:
    if route.get("stage_rank") is not None:
        return int(route.get("stage_rank") or 0)
    return ROUTE_STAGE_MAP.get(str(route.get("route_type") or ""), 5)


def _card_sort_key(route: dict[str, Any]) -> tuple[Any, ...]:
    status = str(route.get("stage_gate_status") or "blocked")
    status_rank = 0 if status in {"actionable", "event_triggered", "waived"} else 1
    return (
        _stage_rank(route),
        status_rank,
        -float(route.get("within_stage_score") or route.get("priority_score") or 0),
        str(route.get("route_id") or ""),
    )
