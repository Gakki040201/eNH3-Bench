"""Grouped, unit-safe literature shadow models for LiNRR v0.2."""

from __future__ import annotations

import math
from typing import Any

from .linrr_predictor import assert_no_group_leakage, grouped_fold_indices, modeling_gate, paper_group
from .linrr_v02 import (
    R0_CATEGORICAL, R0_NUMERIC, R1_NUMERIC, RI_CATEGORICAL,
    assert_unit_safe_feature_schema, validate_finite_matrix,
)


FEATURE_SCHEMA = {
    "MODEL_R0": {"categorical": R0_CATEGORICAL, "numeric": R0_NUMERIC},
    "MODEL_R1": {"categorical": R0_CATEGORICAL, "numeric": R1_NUMERIC},
    "MODEL_RI": {"categorical": RI_CATEGORICAL, "numeric": R1_NUMERIC},
    "excluded_predictive_fields": ["paper_id", "provisional_bundle_id", "journal", "authors", "year", "source_group"],
}


def pipeline(model_name: str, categorical: list[str], numeric: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="__MISSING__", keep_empty_features=True)),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    preprocess = ColumnTransformer([
        ("numeric", numeric_pipe, list(range(len(numeric)))),
        ("categorical", categorical_pipe, list(range(len(numeric), len(numeric) + len(categorical)))),
    ])
    estimators = {
        "DummyRegressor": DummyRegressor(strategy="mean"),
        "Ridge": Ridge(alpha=1.0, solver="lsqr"),
        "RandomForestRegressor": RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=1729, n_jobs=1),
    }
    return Pipeline([("preprocess", preprocess), ("model", estimators[model_name])])


def metrics(y: list[float], prediction: list[float]) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    bounded = [min(100.0, max(0.0, value)) for value in prediction]
    return {
        "mae": float(mean_absolute_error(y, prediction)),
        "rmse": float(math.sqrt(mean_squared_error(y, prediction))),
        "r2": float(r2_score(y, prediction)),
        "bounded_mae_diagnostic": float(mean_absolute_error(y, bounded)),
        "bounded_rmse_diagnostic": float(math.sqrt(mean_squared_error(y, bounded))),
        "fraction_predictions_below_0": sum(value < 0 for value in prediction) / len(prediction),
        "fraction_predictions_above_100": sum(value > 100 for value in prediction) / len(prediction),
    }


def train_grouped_v02(records: list[dict[str, Any]]) -> dict[str, Any]:
    usable = sorted([row for row in records if row.get("model_eligible_fe") and row.get("fe_nh3_percent") is not None], key=lambda row: str(row["record_id"]))
    gate = modeling_gate(usable)
    assert_unit_safe_feature_schema(FEATURE_SCHEMA)
    if not gate["passed"]:
        return {"gate": gate, "feature_schema": FEATURE_SCHEMA, "metrics": [], "predictions": [], "fold_assignments": [], "fold_metrics": [], "predictive_performance": "FAIL"}
    groups = [paper_group(row) for row in usable]
    folds = grouped_fold_indices(groups)
    assert_no_group_leakage(groups, folds)
    fold_by_index = {index: fold for fold, (_, test) in enumerate(folds) for index in test}
    assignments = [{"record_id": row["record_id"], "paper_group": groups[i], "fold": fold_by_index[i]} for i, row in enumerate(usable)]
    y = [float(row["fe_nh3_percent"]) for row in usable]
    predictions_out: list[dict[str, Any]] = []
    metrics_out: list[dict[str, Any]] = []
    fold_metrics: list[dict[str, Any]] = []
    for family in ("MODEL_R0", "MODEL_R1", "MODEL_RI"):
        categorical = list(FEATURE_SCHEMA[family]["categorical"])
        numeric = list(FEATURE_SCHEMA[family]["numeric"])
        fields = numeric + categorical
        X = [[row.get(field) for field in fields] for row in usable]
        for model_name in ("DummyRegressor", "Ridge", "RandomForestRegressor"):
            predicted = [float("nan")] * len(usable)
            for fold, (train, test) in enumerate(folds):
                model = pipeline(model_name, categorical, numeric)
                model.fit([X[i] for i in train], [y[i] for i in train])
                transformed = model.named_steps["preprocess"].transform([X[i] for i in test])
                validate_finite_matrix(transformed)
                fold_pred = [float(value) for value in model.predict([X[i] for i in test])]
                for i, value in zip(test, fold_pred):
                    predicted[i] = value
                if len(test) >= 2:
                    fold_score = metrics([y[i] for i in test], fold_pred)
                else:
                    error = abs(y[test[0]] - fold_pred[0])
                    fold_score = {"mae": error, "rmse": error, "r2": None}
                fold_metrics.append({"feature_family": family, "model": model_name, "fold": fold, "test_groups": sorted({groups[i] for i in test}), "train_groups": sorted({groups[i] for i in train}), **fold_score})
            score = metrics(y, predicted)
            metrics_out.append({"feature_family": family, "model": model_name, "n_rows": len(usable), "n_groups": len(set(groups)), "n_splits": len(folds), **score})
            for i, row in enumerate(usable):
                value = predicted[i]
                predictions_out.append({
                    "record_id": row["record_id"], "v01_record_id": row.get("v01_record_id"),
                    "paper_group": groups[i], "fold": fold_by_index[i], "feature_family": family,
                    "model": model_name, "observed_fe": y[i], "predicted_fe": value,
                    "bounded_prediction": min(100.0, max(0.0, value)), "absolute_error": abs(y[i] - value),
                })
    index = {(row["feature_family"], row["model"]): row for row in metrics_out}
    dummy_mae = index[("MODEL_R0", "DummyRegressor")]["mae"]
    best_non_dummy = min(row["mae"] for row in metrics_out if row["model"] != "DummyRegressor")
    predictive = "PASS" if best_non_dummy < dummy_mae else "FAIL"
    deltas = []
    consistency = []
    for model_name in ("Ridge", "RandomForestRegressor"):
        for first, second in (("MODEL_R0", "MODEL_R1"), ("MODEL_R1", "MODEL_RI")):
            deltas.append({
                "model": model_name, "comparison": f"{first}_TO_{second}",
                "delta_mae": index[(second, model_name)]["mae"] - index[(first, model_name)]["mae"],
                "delta_rmse": index[(second, model_name)]["rmse"] - index[(first, model_name)]["rmse"],
            })
            first_folds = {row["fold"]: row for row in fold_metrics if row["feature_family"] == first and row["model"] == model_name}
            second_folds = {row["fold"]: row for row in fold_metrics if row["feature_family"] == second and row["model"] == model_name}
            improved = sum(second_folds[fold]["mae"] < first_folds[fold]["mae"] for fold in first_folds)
            consistency.append({"model": model_name, "comparison": f"{first}_TO_{second}", "folds_improved": improved, "folds_total": len(first_folds)})
    return {
        "gate": gate, "feature_schema": FEATURE_SCHEMA, "metrics": metrics_out,
        "predictions": predictions_out, "fold_assignments": assignments,
        "fold_metrics": fold_metrics, "predictive_performance": predictive,
        "family_deltas": deltas, "fold_direction_consistency": consistency,
        "no_paper_leakage": True, "processed_matrices_finite": True,
    }
