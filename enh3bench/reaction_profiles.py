"""Reaction-family profiles for eNH3 claim rights and planning."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


REACTION_FAMILIES = [
    "eNRR",
    "LiNRR",
    "NO3RR",
    "NO2RR",
    "NORR",
    "mixed",
    "unclear",
]

PROFILE_FIELDS = (
    "reaction_family",
    "nitrogen_source",
    "product_admission_gates",
    "required_controls",
    "boundary_fields",
    "family_hidden_taxes",
    "family_route_types",
    "experimental_demonstration_allowed",
    "notes",
)

REACTION_FAMILY_PROFILES: dict[str, dict[str, Any]] = {
    "eNRR": {
        "reaction_family": "eNRR",
        "nitrogen_source": "N2",
        "product_admission_gates": [
            "isotope_15N",
            "blank_control",
            "NOx_control",
            "contamination_control",
            "ammonia_quantification",
        ],
        "required_controls": [
            "15N2 isotope validation",
            "Ar blank",
            "N2-free blank",
            "NOx/nitrate/nitrite screening",
            "background NH3 control",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control", "product_state_accounting"],
        "experimental_demonstration_allowed": False,
        "notes": "General N2-to-NH3 electrochemical nitrogen reduction profile.",
    },
    "LiNRR": {
        "reaction_family": "LiNRR",
        "nitrogen_source": "N2 mediated by Li/Li+",
        "product_admission_gates": [
            "isotope_15N",
            "blank_control",
            "NOx_control",
            "contamination_control",
            "ammonia_quantification",
            "operating_field_disclosure",
        ],
        "required_controls": [
            "15N2 isotope validation",
            "Ar blank",
            "N2-free blank",
            "NOx/nitrate/nitrite screening",
            "background NH3 control",
            "electrolyte blank",
            "gas/liquid product accounting",
            "voltage/current/runtime reporting",
        ],
        "boundary_fields": [
            "Li salt",
            "solvent",
            "proton_donor",
            "water_content",
            "SEI/interphase",
            "SSC/GDE",
            "gas_flow",
            "liquid_flow",
            "product_state",
            "HOR/H2 if used",
        ],
        "family_hidden_taxes": [
            "solvent_management_tax",
            "resistance_or_renewal_tax",
            "wetting_outlet_capture_tax",
            "hydrogen_logistics_tax",
            "contamination_tax",
            "measurement_matrix_tax",
        ],
        "family_route_types": [
            "validation_gap_closure",
            "contamination_control",
            "electrolyte_window",
            "interphase_resistance",
            "flow_wetting",
            "HOR_proton_economy",
            "product_state_accounting",
            "stability_failure",
            "process_boundary_probe",
        ],
        "experimental_demonstration_allowed": True,
        "notes": "Boundary-dense Li-mediated NRR profile used for the USTC wet-lab demonstration track.",
    },
    "NO3RR": {
        "reaction_family": "NO3RR",
        "nitrogen_source": "nitrate",
        "product_admission_gates": [
            "nitrate_source_defined",
            "nitrogen_balance",
            "ammonia_quantification",
            "competing_product_tracking",
        ],
        "required_controls": [
            "nitrate/nitrite source accounting",
            "background NH3 control",
            "electrolyte blank",
            "nitrogen mass balance",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Nitrate-to-ammonia electroreduction profile; 15N2 validation is not the default gate.",
    },
    "NO2RR": {
        "reaction_family": "NO2RR",
        "nitrogen_source": "nitrite",
        "product_admission_gates": [
            "nitrite_source_defined",
            "nitrogen_balance",
            "ammonia_quantification",
            "competing_product_tracking",
        ],
        "required_controls": [
            "nitrate/nitrite source accounting",
            "background NH3 control",
            "electrolyte blank",
            "nitrogen mass balance",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Nitrite-to-ammonia electroreduction profile; 15N2 validation is not the default gate.",
    },
    "NORR": {
        "reaction_family": "NORR",
        "nitrogen_source": "NO",
        "product_admission_gates": [
            "NO_source_defined",
            "NOx_balance",
            "ammonia_quantification",
            "competing_product_tracking",
        ],
        "required_controls": [
            "NO source purity",
            "NOx balance",
            "gas handling blank",
            "ammonia quantification",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "NO-to-ammonia electroreduction profile. Gas handling burdens remain audit notes until formalized.",
    },
    "mixed": {
        "reaction_family": "mixed",
        "nitrogen_source": "multiple or ambiguous nitrogen sources",
        "product_admission_gates": ["nitrogen_source_disambiguation", "nitrogen_balance", "ammonia_quantification"],
        "required_controls": ["nitrogen-source accounting", "clarify nitrogen source", "nitrogen mass balance"],
        "boundary_fields": ["nitrogen_source_disambiguation"],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Mixed-source claims require source disambiguation before stronger claim rights.",
    },
    "unclear": {
        "reaction_family": "unclear",
        "nitrogen_source": "unclear",
        "product_admission_gates": ["nitrogen_source_disambiguation", "ammonia_quantification"],
        "required_controls": ["clarify nitrogen source"],
        "boundary_fields": ["nitrogen_source_disambiguation"],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Conservative fallback when the source text does not identify the ammonia nitrogen source.",
    },
}


def normalize_reaction_family(value: str) -> str:
    """Normalize a reaction-family label to a supported family."""

    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    aliases = {
        "": "unclear",
        "unknown": "unclear",
        "not_specified": "unclear",
        "ambiguous": "unclear",
        "mixed_source": "mixed",
        "multiple": "mixed",
        "nrr": "eNRR",
        "enrr": "eNRR",
        "e_nrr": "eNRR",
        "electrochemical_nrr": "eNRR",
        "electrochemical_nitrogen_reduction": "eNRR",
        "li_nrr": "LiNRR",
        "linrr": "LiNRR",
        "li_mediated_nrr": "LiNRR",
        "lithium_mediated_nrr": "LiNRR",
        "lithium_mediated": "LiNRR",
        "no3rr": "NO3RR",
        "no3_rr": "NO3RR",
        "nitrate_reduction": "NO3RR",
        "nitrate_rr": "NO3RR",
        "no2rr": "NO2RR",
        "no2_rr": "NO2RR",
        "nitrite_reduction": "NO2RR",
        "nitrite_rr": "NO2RR",
        "norr": "NORR",
        "no_rr": "NORR",
        "nitric_oxide_reduction": "NORR",
    }
    candidate = aliases.get(text)
    if candidate:
        return candidate
    for family in REACTION_FAMILIES:
        if text == family.casefold():
            return family
    return "unclear"


def infer_reaction_family_from_text(text: str, default: str = "unclear") -> str:
    """Infer a conservative reaction-family label from source text."""

    normalized_default = normalize_reaction_family(default)
    source = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
    if not source:
        return normalized_default

    signals: set[str] = set()
    if _contains_any(source, ["mixed nitrogen source", "multiple nitrogen sources", "nitrate and n2", "nitrite and n2"]):
        signals.add("mixed")
    if _contains_any(source, ["no3rr", "nitrate reduction", "nitrate electroreduction", "nitrate-to-ammonia", "nitrate to ammonia"]):
        signals.add("NO3RR")
    if re.search(r"\bno3\s*(?:-|−|rr|\b)|\bno3-\b|\bno3−\b", source):
        signals.add("NO3RR")
    if _contains_any(source, ["no2rr", "nitrite reduction", "nitrite electroreduction", "nitrite-to-ammonia", "nitrite to ammonia"]):
        signals.add("NO2RR")
    if re.search(r"\bno2\s*(?:-|−|rr|\b)|\bno2-\b|\bno2−\b", source):
        signals.add("NO2RR")
    if _contains_any(source, ["norr", "nitric oxide reduction", "nitric oxide electroreduction", "no-to-ammonia", "no to ammonia", "no-to-nh3", "no to nh3"]):
        signals.add("NORR")
    if re.search(r"\bno\s+(?:electro)?reduction\b", source) and _contains_any(source, ["ammonia", "nh3"]):
        signals.add("NORR")
    if _contains_any(
        source,
        [
            "lithium-mediated",
            "lithium mediated",
            "li-mediated",
            "li mediated",
            "linrr",
            "li-nrr",
            "li nrr",
            "li salt",
            "lithium salt",
            "liclo4",
            "litfsi",
            "lipf6",
            "tetrahydrofuran",
            "thf",
            "solid electrolyte interphase",
            "sei",
        ],
    ):
        signals.add("LiNRR")
    if _contains_any(source, ["n2 reduction", "nitrogen reduction", "dinitrogen", "n2-to-nh3", "n2 to nh3", "15n2"]):
        signals.add("eNRR")
    if re.search(r"\bnrr\b", source) and "LiNRR" not in signals:
        signals.add("eNRR")

    if "mixed" in signals:
        return "mixed"
    if "LiNRR" in signals and signals <= {"LiNRR", "eNRR"}:
        return "LiNRR"
    if len(signals) > 1:
        return "mixed"
    if signals:
        return next(iter(signals))
    return normalized_default


def get_reaction_profile(family: str) -> dict[str, Any]:
    """Return a copy of the reaction-family profile."""

    normalized = normalize_reaction_family(family)
    return deepcopy(REACTION_FAMILY_PROFILES[normalized])


def profile_required_controls(family: str) -> list[str]:
    return list(get_reaction_profile(family)["required_controls"])


def profile_hidden_taxes(family: str) -> list[str]:
    return list(get_reaction_profile(family)["family_hidden_taxes"])


def profile_route_types(family: str) -> list[str]:
    return list(get_reaction_profile(family)["family_route_types"])


def experimental_demonstration_allowed(family: str, lab_profile: dict[str, Any] | None = None) -> bool:
    """Return whether this family is in the current wet-lab demonstration scope."""

    normalized = normalize_reaction_family(family)
    profile_allowed = bool(REACTION_FAMILY_PROFILES[normalized]["experimental_demonstration_allowed"])
    if lab_profile is None:
        return profile_allowed
    demonstrations = lab_profile.get("reaction_family_demonstrations")
    if isinstance(demonstrations, dict) and normalized in demonstrations:
        return bool(demonstrations[normalized])
    allowed_families = lab_profile.get("allowed_reaction_families")
    if isinstance(allowed_families, list) and allowed_families:
        return normalized in {normalize_reaction_family(str(item)) for item in allowed_families}
    return profile_allowed


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)
