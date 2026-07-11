"""Optional constrained LLM refinement for experiment routes."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from enh3bench.llm_clients.base import BaseLLMClient, LLMClientError


REFINABLE_FIELDS = ("hypothesis", "literature_rationale", "failure_diagnosis_tree", "llm_rationale")


def build_route_refinement_prompt(
    routes: list[dict[str, Any]],
    lab_profile: dict[str, Any],
    boundary_summary: dict[str, Any],
) -> list[dict[str, str]]:
    """Build a strict prompt for optional route-wording refinement."""

    system = (
        "You refine structured eNH3 experiment route cards.\n"
        "You may only improve wording, rationale, and failure diagnosis trees.\n"
        "Do not add lab capabilities. Do not remove mandatory controls. Do not increase route priority.\n"
        "Return strict JSON only."
    )
    payload = {
        "routes": routes,
        "lab_profile_summary": {
            "profile_id": lab_profile.get("profile_id") or "",
            "reactor_capabilities": lab_profile.get("reactor_capabilities") or {},
            "analytics": lab_profile.get("analytics") or {},
            "controls": lab_profile.get("controls") or {},
        },
        "boundary_summary": boundary_summary,
        "allowed_refinable_fields": list(REFINABLE_FIELDS),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)},
    ]


def parse_route_refinement_response(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse a strict JSON route refinement response."""

    cleaned = str(text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"json_parse_error: {exc.msg}"
    if not isinstance(parsed, dict):
        return None, "schema_invalid: response must be object"
    refinements = parsed.get("routes")
    if not isinstance(refinements, list):
        return None, "schema_invalid: routes must be list"
    return parsed, None


def refine_routes_with_llm(
    routes: list[dict[str, Any]],
    lab_profile: dict[str, Any],
    client: BaseLLMClient,
    model: str | None = None,
    max_routes: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Refine route wording with an LLM while preserving hard constraints."""

    selected = routes[:max_routes]
    prompt = build_route_refinement_prompt(selected, lab_profile, {"routes": len(selected)})
    try:
        raw = client.chat(prompt, model=model, temperature=0, response_format={"type": "json_object"})
    except LLMClientError as exc:
        return routes, [{"error_type": "llm_client_error", "error": str(exc)}]
    parsed, error = parse_route_refinement_response(raw)
    if error or parsed is None:
        return routes, [{"error_type": "llm_parse_error", "error": error or "unknown parse error", "llm_raw_response": raw}]

    refinements_by_id = {
        str(item.get("route_id") or ""): item
        for item in parsed.get("routes") or []
        if isinstance(item, dict) and str(item.get("route_id") or "").strip()
    }
    refined_routes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for route in routes:
        updated = copy.deepcopy(route)
        refinement = refinements_by_id.get(str(route.get("route_id") or ""))
        if not refinement:
            refined_routes.append(updated)
            continue
        violations = _constraint_violations(route, refinement)
        if violations:
            updated["llm_used"] = False
            updated["llm_refinement_flags"] = violations
            failures.append({"route_id": route.get("route_id"), "error_type": "llm_constraint_violation", "errors": violations})
            refined_routes.append(updated)
            continue
        for field in REFINABLE_FIELDS:
            if field in refinement and refinement[field]:
                updated[field] = refinement[field]
        updated["llm_used"] = True
        updated["llm_model"] = model or getattr(client, "model", None) or "unknown"
        updated["llm_refinement_flags"] = []
        refined_routes.append(updated)
    return refined_routes, failures


def _constraint_violations(route: dict[str, Any], refinement: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if "required_controls" in refinement and _list_values(refinement.get("required_controls")) != _list_values(route.get("required_controls")):
        violations.append("llm_attempted_required_control_change")
    if "feasible_controls" in refinement and set(_list_values(refinement.get("feasible_controls"))) - set(_list_values(route.get("feasible_controls"))):
        violations.append("llm_attempted_capability_addition")
    if "priority_score" in refinement and int(refinement.get("priority_score") or 0) > int(route.get("priority_score") or 0):
        violations.append("llm_attempted_priority_upgrade")
    if "priority_label" in refinement and str(refinement.get("priority_label") or "") != str(route.get("priority_label") or ""):
        violations.append("llm_attempted_priority_label_change")
    if route.get("infeasible_controls") and str(refinement.get("priority_label") or route.get("priority_label")) == "priority_experiment":
        violations.append("llm_attempted_priority_with_infeasible_controls")
    if route.get("infeasible_measurements") and str(refinement.get("priority_label") or route.get("priority_label")) == "priority_experiment":
        violations.append("llm_attempted_priority_with_infeasible_measurements")
    return violations


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
