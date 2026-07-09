"""Shared schema constants and small helpers for eNH3-BoundaryLedger."""

from __future__ import annotations

import math
import re
from typing import Any


TEXT_CLASSES = (
    "primary_performance",
    "primary_performance_with_validation",
    "protocol_guideline",
    "review_table",
    "figure_caption",
    "reference_list",
    "contamination_detection_evidence",
    "contamination_reassignment_evidence",
    "computational_screening",
    "background_context",
    "unknown",
)

SUPPORTED_BOUNDARIES = (
    "unsupported_or_secondary",
    "product_admissibility",
    "cell_metric",
    "reactor_legibility",
    "process_partial",
    "plant_facing_insufficient",
)

CLAIM_TYPES = (
    "performance_claim",
    "validation_claim",
    "reactor_claim",
    "process_claim",
    "protocol_claim",
    "negative_evidence_claim",
    "secondary_summary_claim",
    "unsupported_claim",
)

VALIDATION_GATES = (
    "isotope_15N",
    "blank_control",
    "nox_control",
    "contamination_control",
    "quantification_method",
)

BOUNDARY_FIELDS = {
    "product_admissibility": (
        "ammonia_quantification",
        "isotope_15N",
        "blank_control",
        "nox_control",
        "contamination_control",
    ),
    "cell_metric": (
        "faradaic_efficiency",
        "nh3_yield",
        "current_density",
        "potential_or_voltage",
        "charge_or_runtime",
        "electrode_area",
    ),
    "reactor_legibility": (
        "reactor_type",
        "flow_rate",
        "active_area",
        "GDE_or_SSC",
        "HOR_or_anode_reaction",
        "runtime_or_stability",
        "outlet_product_state",
        "wetting_or_failure_disclosure",
    ),
    "process_partial": (
        "gas_liquid_product_split",
        "capture_route",
        "solvent_inventory",
        "electrolyte_replacement_or_recycle",
        "hydrogen_source_boundary",
        "auxiliary_loads",
        "voltage_basis",
        "first_failure_signal",
    ),
}

HIDDEN_TAX_TYPES = (
    "solvent_management_tax",
    "resistance_or_renewal_tax",
    "wetting_outlet_capture_tax",
    "hydrogen_logistics_tax",
    "contamination_tax",
    "measurement_matrix_tax",
)


def normalize_yes_no(value: Any) -> str:
    """Normalize common control-gate values to yes, no, missing, or unclear."""

    if value is None:
        return "missing"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return "missing"
        return "yes" if float(value) != 0.0 else "no"

    text = re.sub(r"\s+", " ", str(value).strip().casefold())
    if text in {"", "none", "null", "nan", "n/a", "na", "not applicable", "not_applicable"}:
        return "missing"
    if text in {
        "yes",
        "y",
        "true",
        "1",
        "confirmed",
        "present",
        "explicit",
        "explicitly reported",
        "reported",
        "detected",
        "performed",
        "available",
    }:
        return "yes"
    if text in {
        "no",
        "n",
        "false",
        "0",
        "absent",
        "not reported",
        "not_reported",
        "not detected",
        "not performed",
        "unavailable",
    }:
        return "no"
    if text in {"unknown", "unclear", "ambiguous", "inconclusive", "not specified", "not_specified"}:
        return "unclear"
    return "unclear"


def has_explicit_yes(record: dict[str, Any], *keys: str) -> bool:
    """Return True when any named key is explicitly yes-like."""

    return any(normalize_yes_no(record.get(key)) == "yes" for key in keys)


def has_any_value(record: dict[str, Any], *keys: str) -> bool:
    """Return True when any named key contains a substantive value."""

    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text and normalize_yes_no(text) != "missing" and text.casefold() not in {"unknown", "unclear"}:
                return True
            continue
        if isinstance(value, (list, tuple, set, dict)):
            if value:
                return True
            continue
        return True
    return False


def coerce_float(value: Any) -> float | None:
    """Convert a numeric-looking value to float, returning None when unsafe."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def boundary_rank(boundary: str) -> int:
    """Return the ordering rank for a supported boundary."""

    try:
        return SUPPORTED_BOUNDARIES.index(boundary)
    except ValueError:
        return 0


def max_boundary(boundaries: list[str]) -> str:
    """Return the highest ranked supported boundary from a list."""

    valid = [boundary for boundary in boundaries if boundary in SUPPORTED_BOUNDARIES]
    if not valid:
        return "unsupported_or_secondary"
    return max(valid, key=boundary_rank)
