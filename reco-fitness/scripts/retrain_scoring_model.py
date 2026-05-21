"""Re-entraine le scoring ML enrichi par les feedbacks utilisateurs accumules (RF-15).

Usage :
    python scripts/retrain_scoring_model.py
    python scripts/retrain_scoring_model.py --csv data/training/scoring_dataset.csv \\
        --model app/data/scoring_model.pkl \\
        --report data/training/retrain_report.json

Frequence recommandee : mensuelle (cf README). Le pickle n'est remplace que si
le modele entraine sur le dataset enrichi atteint un F1 superieur ou egal au
modele courant ; sinon l'ancien est conserve et un warning est journalise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.exercise_catalog import get_all  # noqa: E402
from app.services.scoring_retrainer import (  # noqa: E402
    build_feedback_rows,
    load_feedbacks_from_mongo,
    load_profiles_from_mongo,
    retrain_and_maybe_replace,
)
from app.services.training_data import derive_vocab  # noqa: E402

DEFAULT_CSV = Path("data/training/scoring_dataset.csv")
DEFAULT_MODEL = Path("app/data/scoring_model.pkl")
DEFAULT_REPORT = Path("data/training/retrain_report.json")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.csv.exists():
        print(
            f"Dataset de base introuvable : {args.csv}. "
            "Lance d'abord `python scripts/generate_training_data.py`.",
            file=sys.stderr,
        )
        return 1

    from pymongo import MongoClient

    mongo_client = MongoClient(settings.MONGO_URI, tz_aware=True)
    pg_session = SessionLocal()
    try:
        mongo_db = mongo_client[settings.MONGO_DATABASE]
        feedbacks = load_feedbacks_from_mongo(mongo_db)
        user_ids = sorted({fb["user_id"] for fb in feedbacks})
        profiles = load_profiles_from_mongo(mongo_db, user_ids)

        catalog = get_all(pg_session)
        vocab = derive_vocab(catalog)
        feedback_rows = build_feedback_rows(
            feedbacks=feedbacks,
            profiles_by_user=profiles,
            catalog_by_id={ex.id: ex for ex in catalog},
            vocab=vocab,
        )
        report = retrain_and_maybe_replace(
            base_csv=args.csv,
            feedback_rows=feedback_rows,
            model_path=args.model,
            report_path=args.report,
        )
    finally:
        pg_session.close()
        mongo_client.close()

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
