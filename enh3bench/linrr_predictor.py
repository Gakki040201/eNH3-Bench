"""Grouped-validation literature shadow predictor for LiNRR v0."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CATEGORICAL_R = [
    "lithium_salt", "solvent", "cosolvent", "proton_donor", "additive",
    "oxygen_condition", "electrode_material", "cell_type",
]
NUMERIC_R = [
    "lithium_salt_concentration_mol_L", "proton_donor_concentration_value",
    "water_content_value", "current_density_mA_cm2", "total_charge_C", "duration_h",
    "temperature_C", "pressure_bar", "gas_flow_sccm", "liquid_flow_mL_min", "electrode_area_cm2",
]
INTERFACE_PROXIES = [
    "interface_sei_characterization_present", "interface_lif_reported",
    "interface_n_containing_sei_reported", "electrolyte_architecture",
]
MIN_FE_ROWS = 25
MIN_PAPER_GROUPS = 5


def paper_group(record: dict[str, Any]) -> str:
    group = record.get("paper_id") or record.get("provisional_bundle_id") or record.get("source_bundle_id")
    if not group:
        raise ValueError(f"Record {record.get('record_id')} has no paper/provisional bundle group")
    return str(group)


def modeling_gate(records: list[dict[str, Any]], target: str = "fe_nh3_percent") -> dict[str, Any]:
    usable = [row for row in records if row.get(target) is not None]
    groups = {paper_group(row) for row in usable}
    reasons = []
    if len(usable) < MIN_FE_ROWS:
        reasons.append(f"eligible FE rows {len(usable)} < {MIN_FE_ROWS}")
    if len(groups) < MIN_PAPER_GROUPS:
        reasons.append(f"unique paper groups {len(groups)} < {MIN_PAPER_GROUPS}")
    return {"passed": not reasons, "row_count": len(usable), "group_count": len(groups), "status": "READY" if not reasons else "INSUFFICIENT_MODELING_DATA", "reasons": reasons}


def secondary_target_assessment(records: list[dict[str, Any]], primary_gate_passed: bool) -> dict[str, Any]:
    rows = [row for row in records if row.get("nh3_rate_value") is not None and row.get("nh3_rate_unit")]
    units = sorted({str(row["nh3_rate_unit"]).strip() for row in rows})
    reasons = []
    if not primary_gate_passed:
        reasons.append("primary FE modeling gate did not pass; milestone stops before fitting")
    if len(units) != 1:
        reasons.append(f"NH3-rate units are not one coherent explicit unit ({len(units)} distinct units)")
    gate = modeling_gate(rows, "nh3_rate_value") if len(units) == 1 else {"passed": False, "row_count": len(rows), "group_count": len({paper_group(row) for row in rows}) if rows else 0}
    reasons.extend(gate.get("reasons", []))
    return {"passed": not reasons and bool(gate.get("passed")), "row_count": len(rows), "group_count": gate.get("group_count", 0), "units": units, "status": "READY" if not reasons and gate.get("passed") else "NOT_TRAINED", "reasons": reasons}


def grouped_fold_indices(groups: list[str], n_splits: int | None = None) -> list[tuple[list[int], list[int]]]:
    from sklearn.model_selection import GroupKFold
    unique = set(groups)
    splits = min(5, len(unique)) if n_splits is None else n_splits
    if splits < 2:
        raise ValueError("At least two paper groups are required")
    dummy = [[0.0]] * len(groups)
    return [(train.tolist(), test.tolist()) for train, test in GroupKFold(n_splits=splits).split(dummy, groups=groups)]


def assert_no_group_leakage(groups: list[str], folds: list[tuple[list[int], list[int]]]) -> None:
    for fold_i, (train, test) in enumerate(folds):
        overlap = {groups[index] for index in train} & {groups[index] for index in test}
        if overlap:
            raise AssertionError(f"Paper leakage in fold {fold_i}: {sorted(overlap)}")


def available_interface_proxies(records: list[dict[str, Any]]) -> list[str]:
    usable = []
    for field in INTERFACE_PROXIES:
        values = [row.get(field) for row in records]
        present = sum(value not in (None, False, "", "unknown") for value in values)
        absent = len(values) - present
        if present >= 5 and absent >= 5:
            usable.append(field)
    return usable


def _pipeline(model_name: str, categorical: list[str], numeric: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric_pipe = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)), ("scale", StandardScaler())])
    categorical_pipe = Pipeline([("impute", SimpleImputer(strategy="constant", fill_value="__MISSING__", keep_empty_features=True)), ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    numeric_indices = list(range(len(numeric)))
    categorical_indices = list(range(len(numeric), len(numeric) + len(categorical)))
    preprocess = ColumnTransformer([("numeric", numeric_pipe, numeric_indices), ("categorical", categorical_pipe, categorical_indices)], remainder="drop")
    if model_name == "DummyRegressor":
        estimator = DummyRegressor(strategy="mean")
    elif model_name == "Ridge":
        estimator = Ridge(alpha=1.0, solver="lsqr")
    elif model_name == "RandomForestRegressor":
        estimator = RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=1729, n_jobs=-1)
    else:
        raise ValueError(f"Unsupported model: {model_name}")
    return Pipeline([("preprocess", preprocess), ("model", estimator)])


def _matrix(records: list[dict[str, Any]], fields: list[str]) -> list[list[Any]]:
    return [[row.get(field) for field in fields] for row in records]


def _metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float | None]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)) if len(y_true) >= 2 else None,
    }


def train_grouped_models(records: list[dict[str, Any]], target: str = "fe_nh3_percent") -> dict[str, Any]:
    usable = sorted((row for row in records if row.get(target) is not None), key=lambda row: str(row["record_id"]))
    gate = modeling_gate(usable, target)
    if not gate["passed"]:
        interface = available_interface_proxies(usable)
        feature_schema = {
            "MODEL_R": {"categorical": CATEGORICAL_R, "numeric": NUMERIC_R},
            "MODEL_RI": {"categorical": CATEGORICAL_R + interface, "numeric": NUMERIC_R, "available_interface_proxies": interface},
            "excluded_predictive_fields": ["paper_id", "provisional_bundle_id", "journal", "year", "authors", "source_group"],
        }
        return {"gate": gate, "a_only_gate": None, "metrics": [], "predictions": [], "fold_assignments": [], "fitted_model": None, "best_model": None, "feature_schema": feature_schema}
    groups = [paper_group(row) for row in usable]
    folds = grouped_fold_indices(groups)
    assert_no_group_leakage(groups, folds)
    interface = available_interface_proxies(usable)
    families = {"MODEL_R": (list(CATEGORICAL_R), list(NUMERIC_R))}
    if interface:
        families["MODEL_RI"] = (list(CATEGORICAL_R) + interface, list(NUMERIC_R))
    fold_by_index: dict[int, int] = {}
    for fold_i, (_, test_indices) in enumerate(folds):
        for index in test_indices:
            fold_by_index[index] = fold_i
    assignments = [{"record_id": row["record_id"], "paper_group": groups[i], "fold": fold_by_index[i], "tier_scope": "A+B"} for i, row in enumerate(usable)]
    all_predictions: list[dict[str, Any]] = []
    all_metrics: list[dict[str, Any]] = []
    y = [float(row[target]) for row in usable]
    models = ["DummyRegressor", "Ridge", "RandomForestRegressor"]
    best: tuple[float, Any, dict[str, Any]] | None = None
    for family, (categorical, numeric) in families.items():
        fields = [*numeric, *categorical]
        X = _matrix(usable, fields)
        for model_name in models:
            predictions = [float("nan")] * len(usable)
            for fold_i, (train_indices, test_indices) in enumerate(folds):
                assert not ({groups[index] for index in train_indices} & {groups[index] for index in test_indices})
                pipeline = _pipeline(model_name, categorical, numeric)
                pipeline.fit([X[index] for index in train_indices], [y[index] for index in train_indices])
                values = pipeline.predict([X[index] for index in test_indices])
                for index, value in zip(test_indices, values):
                    predictions[index] = float(value)
            score = _metrics(y, predictions)
            metric = {"target": target, "tier_scope": "A+B", "feature_family": family, "model": model_name, "n_rows": len(usable), "n_groups": len(set(groups)), "n_splits": len(folds), **score}
            tier_metrics = {}
            for tier in ("TIER_A", "TIER_B"):
                indices = [i for i, row in enumerate(usable) if row.get("eligibility_tier") == tier]
                if len(indices) >= 3:
                    tier_metrics[tier] = _metrics([y[i] for i in indices], [predictions[i] for i in indices])
            metric["metrics_by_source_tier"] = tier_metrics
            all_metrics.append(metric)
            for i, row in enumerate(usable):
                all_predictions.append({"record_id": row["record_id"], "paper_group": groups[i], "fold": fold_by_index[i], "target": target, "observed": y[i], "predicted": predictions[i], "residual": y[i] - predictions[i], "eligibility_tier": row.get("eligibility_tier"), "feature_family": family, "model": model_name, "tier_scope": "A+B"})
            if model_name != "DummyRegressor" and (best is None or float(score["mae"]) < best[0]):
                final = _pipeline(model_name, categorical, numeric)
                final.fit(X, y)
                best = (float(score["mae"]), final, {"feature_family": family, "model": model_name, "categorical": categorical, "numeric": numeric})
    a_only = [row for row in usable if row.get("eligibility_tier") == "TIER_A"]
    a_gate = modeling_gate(a_only, target)
    if a_gate["passed"]:
        a_metrics, a_predictions, a_assignments = _evaluate_additional_scope(a_only, target, families, "A-only")
        all_metrics.extend(a_metrics)
        all_predictions.extend(a_predictions)
        assignments.extend(a_assignments)
    return {
        "gate": gate, "a_only_gate": a_gate, "metrics": all_metrics, "predictions": all_predictions,
        "fold_assignments": assignments, "fitted_model": best[1] if best else None,
        "best_model": best[2] if best else None,
        "feature_schema": {"MODEL_R": {"categorical": CATEGORICAL_R, "numeric": NUMERIC_R}, "MODEL_RI": {"categorical": CATEGORICAL_R + interface, "numeric": NUMERIC_R, "available_interface_proxies": interface}, "excluded_predictive_fields": ["paper_id", "provisional_bundle_id", "journal", "year", "authors", "source_group"]},
    }


def _evaluate_additional_scope(records: list[dict[str, Any]], target: str, families: dict[str, tuple[list[str], list[str]]], scope: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate an additional gated scope without changing the A+B final fit."""
    usable = sorted(records, key=lambda row: str(row["record_id"]))
    groups = [paper_group(row) for row in usable]
    folds = grouped_fold_indices(groups)
    assert_no_group_leakage(groups, folds)
    fold_by_index = {index: fold_i for fold_i, (_, test) in enumerate(folds) for index in test}
    assignments = [{"record_id": row["record_id"], "paper_group": groups[i], "fold": fold_by_index[i], "tier_scope": scope} for i, row in enumerate(usable)]
    y = [float(row[target]) for row in usable]
    metrics: list[dict[str, Any]] = []
    predictions_out: list[dict[str, Any]] = []
    for family, (categorical, numeric) in families.items():
        X = _matrix(usable, [*numeric, *categorical])
        for model_name in ("DummyRegressor", "Ridge", "RandomForestRegressor"):
            predictions = [float("nan")] * len(usable)
            for train, test in folds:
                pipeline = _pipeline(model_name, categorical, numeric)
                pipeline.fit([X[i] for i in train], [y[i] for i in train])
                for index, value in zip(test, pipeline.predict([X[i] for i in test])):
                    predictions[index] = float(value)
            metrics.append({"target": target, "tier_scope": scope, "feature_family": family, "model": model_name, "n_rows": len(usable), "n_groups": len(set(groups)), "n_splits": len(folds), **_metrics(y, predictions), "metrics_by_source_tier": {}})
            predictions_out.extend({"record_id": row["record_id"], "paper_group": groups[i], "fold": fold_by_index[i], "target": target, "observed": y[i], "predicted": predictions[i], "residual": y[i] - predictions[i], "eligibility_tier": row.get("eligibility_tier"), "feature_family": family, "model": model_name, "tier_scope": scope} for i, row in enumerate(usable))
    return metrics, predictions_out, assignments


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(repo: str | Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def software_versions() -> dict[str, str]:
    import numpy
    import sklearn
    return {"python": platform.python_version(), "platform": platform.platform(), "scikit_learn": sklearn.__version__, "numpy": numpy.__version__}


def write_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def write_training_outputs(result: dict[str, Any], output_dir: str | Path, dataset_path: str | Path, repo: str | Path, target: str = "fe_nh3_percent") -> None:
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite modeling output: {output_dir}")
    output_dir.mkdir(parents=True)
    feature_path = output_dir / "feature_schema.json"
    feature_path.write_text(json.dumps(result["feature_schema"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metrics_payload = {"model_type": "literature shadow model", "gate": result["gate"], "a_only_gate": result.get("a_only_gate"), "secondary_target_gate": result.get("secondary_target_gate"), "metrics": result["metrics"]}
    (output_dir / "model_metrics.json").write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(result["metrics"], output_dir / "model_comparison.csv")
    write_csv(result["predictions"], output_dir / "oof_predictions.csv")
    write_csv(result["fold_assignments"], output_dir / "fold_assignments.csv")
    manifest = {
        "model_type": "literature shadow model", "dataset_path": str(Path(dataset_path).resolve()),
        "dataset_sha256": sha256_file(dataset_path), "code_commit": git_commit(repo), "feature_schema": result["feature_schema"],
        "target": target, "groups": "paper_id or provisional_bundle_id", "fold_definition": "GroupKFold(n_splits=min(5, unique paper groups)); no row-random split",
        "model_hyperparameters": {"DummyRegressor": {"strategy": "mean"}, "Ridge": {"alpha": 1.0, "solver": "lsqr"}, "RandomForestRegressor": {"n_estimators": 300, "min_samples_leaf": 2, "random_state": 1729}},
        "software_versions": software_versions(), "timestamp_utc": datetime.now(timezone.utc).isoformat(), "gate": result["gate"], "secondary_target_gate": result.get("secondary_target_gate"), "best_model": result.get("best_model"),
    }
    (output_dir / "training_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "training_report.md").write_text(training_report(result), encoding="utf-8")
    if result.get("fitted_model") is not None:
        import joblib
        joblib.dump(result["fitted_model"], output_dir / "model.joblib")


def training_report(result: dict[str, Any]) -> str:
    gate = result["gate"]
    lines = ["# LiNRR literature shadow model v0", "", "This is a literature shadow model. It is not prospective proof, an autonomous design model, a validated optimization engine, or a discovery claim.", ""]
    if not gate["passed"]:
        lines.extend(["## INSUFFICIENT_MODELING_DATA", "", *[f"- {reason}" for reason in gate["reasons"]], "", "The dataset and gap reports were produced, but no estimator was fitted.", ""])
        secondary = result.get("secondary_target_gate") or {}
        if secondary:
            lines.extend(["## Secondary NH3-rate target", "", *[f"- {reason}" for reason in secondary.get("reasons", [])], ""])
        return "\n".join(lines)
    lines.extend([f"Grouped out-of-fold validation used {gate['row_count']} FE rows across {gate['group_count']} paper groups. Every paper is wholly contained in one fold.", "", "| Features | Model | MAE | RMSE | R2 |", "|---|---|---:|---:|---:|"])
    for metric in result["metrics"]:
        lines.append(f"| {metric['feature_family']} | {metric['model']} | {metric['mae']:.4g} | {metric['rmse']:.4g} | {metric['r2']:.4g} |")
    has_ri = any(metric["feature_family"] == "MODEL_RI" for metric in result["metrics"])
    lines.extend(["", "## Interface-aware comparison", ""])
    if not has_ri:
        lines.append("Interface proxies were too sparse to support a defensible MODEL_RI comparison; no comparison was forced.")
    else:
        best_r = min((m for m in result["metrics"] if m["tier_scope"] == "A+B" and m["feature_family"] == "MODEL_R" and m["model"] != "DummyRegressor"), key=lambda m: m["mae"])
        best_ri = min((m for m in result["metrics"] if m["tier_scope"] == "A+B" and m["feature_family"] == "MODEL_RI" and m["model"] != "DummyRegressor"), key=lambda m: m["mae"])
        direction = "improved" if best_ri["mae"] < best_r["mae"] else "did not improve"
        lines.append(f"The best interface-aware model {direction} grouped out-of-paper MAE relative to the best recipe-only model ({best_ri['mae']:.4g} versus {best_r['mae']:.4g}). This is diagnostic, not causal evidence.")
    lines.extend(["", "A-only modeling is reported only when its independent minimum-data gate passes. R2 should not be emphasized for small samples.", ""])
    return "\n".join(lines)
