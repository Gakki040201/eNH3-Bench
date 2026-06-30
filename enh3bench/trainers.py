"""Small local model trainers for eNH3-TriageBench."""

from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any


SKLEARN_INSTALL_COMMAND = r"C:\Python314\python.exe -m pip install scikit-learn joblib"


def dependencies_available() -> bool:
    """Return whether optional local training dependencies are importable."""

    return importlib.util.find_spec("sklearn") is not None and importlib.util.find_spec("joblib") is not None


def missing_dependency_message() -> str:
    """Return the requested installation instruction for training dependencies."""

    return f"Install local training dependencies with:\n{SKLEARN_INSTALL_COMMAND}"


def train_source_span_classifier(
    training_csv: str | Path,
    model_output: str | Path,
    report_output: str | Path,
) -> dict[str, Any]:
    """Train a TF-IDF source-span text classifier or a smoke fallback model."""

    if not dependencies_available():
        raise RuntimeError(missing_dependency_message())

    import joblib  # type: ignore[import-not-found]
    from sklearn.dummy import DummyClassifier  # type: ignore[import-not-found]
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-not-found]
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-not-found]
    from sklearn.metrics import accuracy_score, classification_report  # type: ignore[import-not-found]
    from sklearn.model_selection import train_test_split  # type: ignore[import-not-found]
    from sklearn.pipeline import Pipeline  # type: ignore[import-not-found]

    rows = _load_csv(Path(training_csv))
    examples = [
        (row.get("source_text", ""), row.get("human_text_class") or row.get("machine_text_class") or "")
        for row in rows
        if (row.get("source_text") or "").strip()
        and (row.get("human_text_class") or row.get("machine_text_class") or "").strip()
    ]
    if not examples:
        raise ValueError(f"No labeled source-span rows found in {training_csv}")

    texts = [text for text, _label in examples]
    labels = [label for _text, label in examples]
    smoke_warning = len(examples) < 20
    unique_labels = sorted(set(labels))
    classifier: Any
    model_type: str
    if len(unique_labels) < 2:
        classifier = DummyClassifier(strategy="most_frequent")
        model_type = "tfidf_dummy_smoke"
        smoke_warning = True
    else:
        classifier = LogisticRegression(max_iter=1000)
        model_type = "tfidf_logistic_regression"

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
            ("classifier", classifier),
        ]
    )
    split = _safe_split(texts, labels, train_test_split)
    if split is None:
        x_train, x_test, y_train, y_test = texts, texts, labels, labels
        evaluation_mode = "training-set smoke evaluation"
        smoke_warning = True
    else:
        x_train, x_test, y_train, y_test = split
        evaluation_mode = "holdout evaluation"

    pipeline.fit(x_train, y_train)
    predictions = list(pipeline.predict(x_test))
    accuracy = float(accuracy_score(y_test, predictions))
    report_text = classification_report(y_test, predictions, zero_division=0)

    model_output = Path(model_output)
    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "kind": "source_span_classifier",
            "model_type": model_type,
            "model": pipeline,
            "labels": unique_labels,
        },
        model_output,
    )

    report = _training_report(
        title="Source Span Classifier Training",
        model_type=model_type,
        row_count=len(examples),
        label_counts=Counter(labels),
        evaluation_mode=evaluation_mode,
        accuracy=accuracy,
        classification_report_text=report_text,
        smoke_warning=smoke_warning,
    )
    report_output = Path(report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8", newline="\n")

    return {
        "status": "trained",
        "model_path": str(model_output),
        "report_path": str(report_output),
        "row_count": len(examples),
        "model_type": model_type,
        "accuracy": accuracy,
        "smoke_warning": smoke_warning,
    }


def train_triage_ranker(
    training_csv: str | Path,
    model_output: str | Path,
    report_output: str | Path,
) -> dict[str, Any]:
    """Train a small local recommendation model for triage ranking labels."""

    if not dependencies_available():
        raise RuntimeError(missing_dependency_message())

    import joblib  # type: ignore[import-not-found]
    from sklearn.dummy import DummyClassifier  # type: ignore[import-not-found]
    from sklearn.feature_extraction import DictVectorizer  # type: ignore[import-not-found]
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-not-found]
    from sklearn.metrics import accuracy_score, classification_report  # type: ignore[import-not-found]
    from sklearn.model_selection import train_test_split  # type: ignore[import-not-found]
    from sklearn.pipeline import Pipeline  # type: ignore[import-not-found]

    rows = _load_csv(Path(training_csv))
    examples = [
        (triage_feature_dict(row), row.get("human_recommendation") or row.get("machine_recommendation") or "")
        for row in rows
        if (row.get("human_recommendation") or row.get("machine_recommendation") or "").strip()
    ]
    if not examples:
        raise ValueError(f"No labeled triage rows found in {training_csv}")

    features = [feature for feature, _label in examples]
    labels = [label for _feature, label in examples]
    smoke_warning = len(examples) < 20
    unique_labels = sorted(set(labels))
    classifier: Any
    model_type: str
    if len(unique_labels) < 2:
        classifier = DummyClassifier(strategy="most_frequent")
        model_type = "dict_dummy_smoke"
        smoke_warning = True
    else:
        classifier = LogisticRegression(max_iter=1000)
        model_type = "dict_logistic_regression"

    pipeline = Pipeline(
        [
            ("features", DictVectorizer(sparse=True)),
            ("classifier", classifier),
        ]
    )
    split = _safe_split(features, labels, train_test_split)
    if split is None:
        x_train, x_test, y_train, y_test = features, features, labels, labels
        evaluation_mode = "training-set smoke evaluation"
        smoke_warning = True
    else:
        x_train, x_test, y_train, y_test = split
        evaluation_mode = "holdout evaluation"

    pipeline.fit(x_train, y_train)
    predictions = list(pipeline.predict(x_test))
    accuracy = float(accuracy_score(y_test, predictions))
    report_text = classification_report(y_test, predictions, zero_division=0)

    model_output = Path(model_output)
    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "kind": "triage_ranker",
            "model_type": model_type,
            "model": pipeline,
            "labels": unique_labels,
        },
        model_output,
    )

    report = _training_report(
        title="Triage Ranker Training",
        model_type=model_type,
        row_count=len(examples),
        label_counts=Counter(labels),
        evaluation_mode=evaluation_mode,
        accuracy=accuracy,
        classification_report_text=report_text,
        smoke_warning=smoke_warning,
    )
    report_output = Path(report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8", newline="\n")

    return {
        "status": "trained",
        "model_path": str(model_output),
        "report_path": str(report_output),
        "row_count": len(examples),
        "model_type": model_type,
        "accuracy": accuracy,
        "smoke_warning": smoke_warning,
    }


def triage_feature_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one triage training/prediction row into model features."""

    return {
        "reaction_family": str(row.get("reaction_family") or ""),
        "FE_percent": _float_or_zero(row.get("FE_percent") or row.get("faradaic_efficiency_percent")),
        "EE_percent": _float_or_zero(row.get("EE_percent") or row.get("energy_efficiency_percent")),
        "NH3_yield": _float_or_zero(row.get("NH3_yield") or row.get("nh3_yield_value")),
        "has_FE": bool(str(row.get("FE_percent") or row.get("faradaic_efficiency_percent") or "").strip()),
        "has_NH3_yield": bool(str(row.get("NH3_yield") or row.get("nh3_yield_value") or "").strip()),
        "isotope_validation": str(row.get("isotope_validation") or ""),
        "blank_control": str(row.get("blank_control") or ""),
        "contamination_control": str(row.get("contamination_control") or ""),
        "nox_screening": str(row.get("nox_screening") or ""),
        "reactor_type": str(row.get("reactor_type") or ""),
        "engineering_flags": str(row.get("engineering_flags") or ""),
    }


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _safe_split(items: list[Any], labels: list[str], train_test_split: Any) -> tuple[list[Any], list[Any], list[str], list[str]] | None:
    if len(items) < 4 or len(set(labels)) < 2:
        return None
    counts = Counter(labels)
    stratify = labels if min(counts.values()) >= 2 else None
    try:
        return train_test_split(items, labels, test_size=0.25, random_state=7, stratify=stratify)
    except ValueError:
        return None


def _training_report(
    title: str,
    model_type: str,
    row_count: int,
    label_counts: Counter[str],
    evaluation_mode: str,
    accuracy: float,
    classification_report_text: str,
    smoke_warning: bool,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Model type: `{model_type}`",
        f"- Labeled rows: {row_count}",
        f"- Evaluation mode: {evaluation_mode}",
        f"- Accuracy: {accuracy:.3f}",
        f"- Label counts: {json.dumps(dict(sorted(label_counts.items())), sort_keys=True)}",
    ]
    if smoke_warning:
        lines.append("- Warning: fewer than 20 labeled rows or one label class; this is a smoke model only.")
    lines.extend(["", "## Classification Report", "", "```text", classification_report_text.strip(), "```", ""])
    return "\n".join(lines)


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
