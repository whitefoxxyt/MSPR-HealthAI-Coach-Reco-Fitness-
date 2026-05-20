"""Pipeline d'entrainement du scoring ML : CSV -> RandomForest + metrics report."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    f1_score,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

from app.services.training_data import Vocab

CLASSIFICATION_THRESHOLD = 0.5


def _vocab_from_columns(df: pd.DataFrame) -> Vocab:
    """Reconstitue le Vocab a partir des prefixes de colonnes du dataset encode."""

    def _extract(prefix: str) -> list[str]:
        return [c.removeprefix(prefix) for c in df.columns if c.startswith(prefix)]

    return Vocab(
        muscles=_extract("ex_muscle_"),
        equipment=_extract("ex_equipment_"),
        categories=_extract("ex_category_"),
        difficulties=_extract("ex_difficulty_"),
    )


def _split_60_20_20(
    X: np.ndarray, y: np.ndarray, random_state: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.4, random_state=random_state
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=random_state
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


def _classification_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Precision/rappel/F1 sur "score > 0.5" (classification appropriate vs not)."""
    true_cls = (y_true > CLASSIFICATION_THRESHOLD).astype(int)
    pred_cls = (y_pred > CLASSIFICATION_THRESHOLD).astype(int)
    return {
        "precision": float(precision_score(true_cls, pred_cls, zero_division=0)),
        "recall": float(recall_score(true_cls, pred_cls, zero_division=0)),
        "f1": float(f1_score(true_cls, pred_cls, zero_division=0)),
    }


def train_and_persist(
    csv_path: Path,
    model_path: Path,
    report_path: Path,
) -> None:
    """Entraine un RandomForestRegressor sur le CSV et persiste le bundle + report."""
    df = pd.read_csv(csv_path)
    feature_columns = [c for c in df.columns if c not in ("label", "exercise_id")]
    X = df[feature_columns].to_numpy()
    y = df["label"].to_numpy()

    X_train, X_val, X_test, y_train, y_val, y_test = _split_60_20_20(X, y, random_state=42)

    model = RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42)
    model.fit(X_train, y_train)

    y_val_pred = model.predict(X_val)
    y_test_pred = model.predict(X_test)
    report = {
        "val": {
            "mse": float(mean_squared_error(y_val, y_val_pred)),
            "r2": float(r2_score(y_val, y_val_pred)),
        },
        "test": _classification_metrics(y_test, y_test_pred),
    }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "vocab": _vocab_from_columns(df),
            "feature_columns": feature_columns,
        },
        model_path,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
