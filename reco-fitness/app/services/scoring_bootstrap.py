"""Entrainement du modele de scoring au demarrage quand le pickle est absent.

scoring_model.pkl est gitignore (regenerable par script) : l'image Docker ne
l'embarque pas. Sans lui, le premier appel premium leve un FileNotFoundError
dans scoring_ml.get_model. Ce module reutilise la meme chaine que
scripts/train_scoring_model.py (dataset synthetique depuis le catalogue PG,
puis train_and_persist) pour garantir le pickle en deploiement.
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

from app.db.session import SessionLocal
from app.services import scoring_ml
from app.services.exercise_catalog import get_all
from app.services.scoring_trainer import train_and_persist
from app.services.training_data import build_dataset, write_dataset

logger = logging.getLogger(__name__)

# Memes valeurs par defaut que scripts/generate_training_data.py.
_N_PROFILES = 25
_SEED = 42


def ensure_scoring_model() -> bool:
    """Garantit la presence de scoring_model.pkl, en l'entrainant si besoin.

    Ne leve jamais : en cas d'echec (PG injoignable, catalogue vide), retourne
    False et laisse le comportement actuel (erreur explicite au premier appel
    premium via scoring_ml.get_model).
    """
    if scoring_ml.MODEL_PATH.exists():
        logger.info("scoring_bootstrap : modele deja present, rien a faire.")
        return True
    started = time.perf_counter()
    try:
        db = SessionLocal()
        try:
            exercises = get_all(db)
        finally:
            db.close()
        if not exercises:
            logger.warning("scoring_bootstrap : catalogue PG vide, modele non entraine.")
            return False
        df = build_dataset(exercises, n_profiles=_N_PROFILES, seed=_SEED)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "scoring_dataset.csv"
            write_dataset(df, csv_path)
            train_and_persist(csv_path, scoring_ml.MODEL_PATH, Path(tmp) / "training_report.json")
        scoring_ml.reset_model()
        logger.info(
            "scoring_bootstrap : modele entraine en %.1f s (%d exercices, %d profils).",
            time.perf_counter() - started,
            len(exercises),
            _N_PROFILES,
        )
        return True
    except Exception:
        logger.exception("scoring_bootstrap : echec de l'entrainement, scoring ML indisponible.")
        return False
