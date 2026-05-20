"""Genere un dataset synthetique (exercise, profile) -> score pour entrainer le modele ML.

Usage :
    python scripts/generate_training_data.py
    python scripts/generate_training_data.py --n-profiles 500 --seed 42 \\
        --out data/training/scoring_dataset.csv

Le dataset cible >= 5000 lignes : avec ~200 exos en BDD x 25 profils = 5000.
Output gitignore, regenerable a tout moment.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permet l'execution depuis la racine du projet (`python scripts/...`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.exercise_catalog import get_all  # noqa: E402
from app.services.training_data import (  # noqa: E402
    build_dataset,
    describe_dataset,
    write_dataset,
)

DEFAULT_OUTPUT = Path("data/training/scoring_dataset.csv")
DEFAULT_N_PROFILES = 25
DEFAULT_SEED = 42


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-profiles", type=int, default=DEFAULT_N_PROFILES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def _print_stats(stats: dict[str, object]) -> None:
    print(f"Rows generated     : {stats['n_rows']}")
    print(
        f"Label distribution : mean={stats['label_mean']:.3f} "
        f"std={stats['label_std']:.3f} min={stats['label_min']:.3f} "
        f"max={stats['label_max']:.3f}"
    )
    print("Rows per health goal :")
    for goal, count in sorted(stats["rows_per_goal"].items()):  # type: ignore[union-attr]
        print(f"  {goal:<18s} {count}")
    print("Rows per experience level :")
    for level, count in sorted(stats["rows_per_level"].items()):  # type: ignore[union-attr]
        print(f"  {level:<18s} {count}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    db = SessionLocal()
    try:
        exercises = get_all(db)
    finally:
        db.close()

    if not exercises:
        print("Catalogue d'exercices vide -- impossible de generer le dataset.", file=sys.stderr)
        return 1

    print(f"Loaded {len(exercises)} exercises from catalog.")
    print(f"Generating {args.n_profiles} synthetic profiles (seed={args.seed})...")

    df = build_dataset(exercises, n_profiles=args.n_profiles, seed=args.seed)
    write_dataset(df, args.out)

    print(f"Dataset written to {args.out}")
    _print_stats(describe_dataset(df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
