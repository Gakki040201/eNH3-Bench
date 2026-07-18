from __future__ import annotations

from pathlib import Path


def write_document(root: Path, name: str = "paper", *, title: str | None = None, body: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    value = body or f"""# {title or 'Electrochemical nitrogen reduction to ammonia'}

## Abstract

In this work, we report electrochemical nitrogen reduction to ammonia.

## Introduction

Ammonia is an important chemical. Smith et al. reported earlier catalysts.

## Methods

Ammonia was quantified using the indophenol colorimetric assay. An argon blank control was performed.

## Results

We measured an ammonia yield rate of 10 ug h-1 and a Faradaic efficiency of 50% for our catalyst.

## References

Smith et al. Review of nitrogen reduction, 2020.
"""
    path = root / f"{name}.md"
    path.write_text(value, encoding="utf-8", newline="\n")
    return path


def write_fixture_corpus(root: Path) -> None:
    specifications = {
        "enrr_primary": ("Electrochemical nitrogen reduction to ammonia", "N2 reduction"),
        "linrr_primary": ("Lithium-mediated nitrogen reduction to ammonia", "Li-mediated N2 reduction"),
        "no3rr_primary": ("Electrochemical nitrate reduction to ammonia", "nitrate reduction"),
        "review": ("A review of electrochemical ammonia synthesis", "This review surveys prior reports"),
        "off_target": ("Electrochemical oxygen evolution", "oxygen evolution reaction"),
        "trap_only": ("Gas handling for nitrogen reduction", "acid trap and gas purification"),
        "quantification": ("Ammonia measurement in electrochemistry", "indophenol quantification of ammonia"),
        "external_cited": ("Catalysts for nitrogen reduction", "Smith et al. reported ammonia yield"),
        "structured_conflict": ("Controls for nitrogen reduction", "No ammonia quantification was performed"),
        "unclear_family": ("Electrochemical catalyst study", "electrochemical measurements"),
    }
    for name, (title, focus) in specifications.items():
        review_language = "This review surveys prior studies." if name == "review" else "In this work, we report new experiments."
        if name == "trap_only":
            result = "The gas stream passed through an acid trap for purification."
        elif name == "off_target":
            result = "We measured an oxygen evolution current density of 10 mA cm-2."
        elif name == "external_cited":
            result = "Smith et al. reported an ammonia yield rate of 10 ug h-1."
        else:
            result = "We measured an ammonia yield rate of 10 ug h-1 and a Faradaic efficiency of 50%."
        if name == "off_target":
            methods = "An oxygen evolution electrode was tested in alkaline electrolyte."
        elif name == "trap_only":
            methods = "The inlet gas passed through an acid trap and purification train."
        else:
            methods = f"Ammonia was quantified using the indophenol colorimetric assay. {focus}."
        body = f"""# {title}

## Abstract

{review_language} The focus is {focus}.

## Introduction

Smith et al. reported related literature.

## Methods

{methods}

## Results

{result}

## References

Smith et al. Prior work, 2020.
"""
        write_document(root, name, body=body)
