"""Re-entrainement du scoring ML enrichi par les feedbacks utilisateurs (RF-15)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services.exercise_catalog import Exercise
from app.services.scoring_trainer import (
    _classification_metrics,
    _vocab_from_columns,
    split_60_20_20,
)
from app.services.training_data import Vocab, encode_pair

HISTORY_COLLECTION = "recommendation_history"
PROFILES_COLLECTION = "user_fitness_profiles"

FEEDBACK_LABEL_DIVISOR = 5.0

logger = logging.getLogger(__name__)


def build_feedback_rows(
    feedbacks: list[dict],
    profiles_by_user: dict[str, FitnessProfileRequest],
    catalog_by_id: dict[int, Exercise],
    vocab: Vocab,
) -> pd.DataFrame:
    """Encode chaque feedback utilisable en ligne (exercise, profile) + label=score/5."""
    rows: list[dict] = []
    for fb in feedbacks:
        exercise_id = fb.get("exercise_id")
        if exercise_id is None:
            # Feedback program-level : pas d'exercice cible, donc pas exploitable.
            continue
        exercise = catalog_by_id.get(exercise_id)
        if exercise is None:
            # Exercice retire du catalogue PG depuis la generation du programme.
            continue
        profile = profiles_by_user.get(fb["user_id"])
        if profile is None:
            # Profil supprime ou jamais cree : pas de features cote utilisateur.
            continue
        label = fb["feedback_score"] / FEEDBACK_LABEL_DIVISOR
        rows.append(encode_pair(exercise, profile, score=label, vocab=vocab))
    return pd.DataFrame(rows)


def _profile_from_doc(doc: dict) -> FitnessProfileRequest:
    """Reconstitue un FitnessProfileRequest a partir d'un document Mongo."""
    return FitnessProfileRequest(
        health_goal_fitness=HealthGoalFitness(doc["health_goal_fitness"]),
        experience_level=ExperienceLevel(doc["experience_level"]),
        equipment=doc.get("equipment", []),
        limitations=doc.get("limitations", []),
        preferences=SessionPreferences(**doc.get("preferences", {})),
    )


def load_feedbacks_from_mongo(db) -> list[dict]:
    """Charge les feedbacks granulaires (avec exercise_id non null) de recommendation_history."""
    return list(
        db[HISTORY_COLLECTION].find(
            {"exercise_id": {"$ne": None}},
            {
                "_id": 0,
                "user_id": 1,
                "program_id": 1,
                "exercise_id": 1,
                "feedback_score": 1,
            },
        )
    )


def load_profiles_from_mongo(
    db, user_ids: list[str]
) -> dict[str, FitnessProfileRequest]:
    """Charge les profils fitness des utilisateurs en parametre, indexes par user_id."""
    if not user_ids:
        return {}
    cursor = db[PROFILES_COLLECTION].find({"user_id": {"$in": user_ids}}, {"_id": 0})
    return {doc["user_id"]: _profile_from_doc(doc) for doc in cursor}


def should_replace_model(old_f1: float | None, new_f1: float) -> bool:
    """Politique de remplacement : on remplace si pas d'ancien modele ou si new >= old."""
    if old_f1 is None:
        return True
    return new_f1 >= old_f1


def _evaluate(model, X_test: np.ndarray, y_test: np.ndarray) -> tuple[float, float]:
    pred = model.predict(X_test)
    metrics = _classification_metrics(y_test, pred)
    return metrics["f1"], float(r2_score(y_test, pred))


def _load_old_metrics(
    model_path: Path,
    feature_columns: list[str],
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> tuple[float | None, float | None]:
    """Charge le modele existant et l'evalue sur le test set commun.

    Retourne (None, None) si pas de modele courant ou si la liste de colonnes
    a change (vocab incompatible -- on traite alors comme un premier run).
    """
    if not model_path.exists():
        return None, None
    old_bundle = joblib.load(model_path)
    if old_bundle.get("feature_columns") != feature_columns:
        logger.warning(
            "feature_columns du modele courant differents du dataset, "
            "evaluation impossible : on traite comme un premier run."
        )
        return None, None
    return _evaluate(old_bundle["model"], X_test, y_test)


def retrain_and_maybe_replace(
    base_csv: Path,
    feedback_rows: pd.DataFrame,
    model_path: Path,
    report_path: Path,
    random_state: int = 42,
) -> dict:
    """Pipeline : entraine sur (synth + feedbacks), compare au modele courant, remplace si meilleur.

    Returns:
        {"old_f1", "new_f1", "old_r2", "new_r2", "replaced", "n_feedback_used"}.
    """
    base_df = pd.read_csv(base_csv)
    n_feedback_used = int(len(feedback_rows))
    if n_feedback_used > 0:
        df = pd.concat([base_df, feedback_rows], ignore_index=True)
    else:
        df = base_df

    feature_columns = [c for c in df.columns if c not in ("label", "exercise_id")]
    X = df[feature_columns].to_numpy()
    y = df["label"].to_numpy()
    X_train, X_val, X_test, y_train, y_val, y_test = split_60_20_20(
        X, y, random_state=random_state
    )

    new_model = RandomForestRegressor(
        n_estimators=200, max_depth=15, random_state=random_state
    )
    new_model.fit(X_train, y_train)
    new_f1, new_r2 = _evaluate(new_model, X_test, y_test)
    old_f1, old_r2 = _load_old_metrics(model_path, feature_columns, X_test, y_test)

    replaced = should_replace_model(old_f1, new_f1)
    if replaced:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": new_model,
                "vocab": _vocab_from_columns(df),
                "feature_columns": feature_columns,
            },
            model_path,
        )
    else:
        logger.warning(
            "Nouveau modele moins bon que l'ancien (new_f1=%.4f < old_f1=%.4f), "
            "pickle conserve.",
            new_f1,
            old_f1,
        )

    report = {
        "old_f1": old_f1,
        "new_f1": new_f1,
        "old_r2": old_r2,
        "new_r2": new_r2,
        "replaced": replaced,
        "n_feedback_used": n_feedback_used,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    return report
