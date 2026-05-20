"""Entraine le modele de scoring ML (RandomForest) sur `data/training/scoring_dataset.csv`.

Usage :
    python scripts/train_scoring_model.py
    python scripts/train_scoring_model.py --csv data/training/scoring_dataset.csv \\
        --model app/data/scoring_model.pkl \\
        --report data/training/training_report.json

Pre-requis : avoir genere le dataset via `python scripts/generate_training_data.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scoring_trainer import train_and_persist  # noqa: E402

DEFAULT_CSV = Path("data/training/scoring_dataset.csv")
DEFAULT_MODEL = Path("app/data/scoring_model.pkl")
DEFAULT_REPORT = Path("data/training/training_report.json")


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
            f"Dataset introuvable : {args.csv}. "
            "Lance d'abord `python scripts/generate_training_data.py`.",
            file=sys.stderr,
        )
        return 1

    print(f"Training on {args.csv} ...")
    train_and_persist(args.csv, args.model, args.report)

    report = json.loads(args.report.read_text())
    print(f"Model     : {args.model}")
    print(f"Report    : {args.report}")
    print(f"Validation: MSE={report['val']['mse']:.4f}  R2={report['val']['r2']:.4f}")
    test = report["test"]
    print(
        f"Test (>0.5): P={test['precision']:.3f}  R={test['recall']:.3f}  "
        f"F1={test['f1']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
