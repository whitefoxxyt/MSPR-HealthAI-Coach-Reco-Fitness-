"""Evalue le moteur de recommandations fitness sur les 7 metriques du PRD (RF-14).

Usage :
    python scripts/eval_metrics.py
    python scripts/eval_metrics.py --n-profiles 100 --seed 42 --out docs
    python scripts/eval_metrics.py --synthetic 120  # catalogue synthetique offline

Sorties (sous `--out`, defaut `docs/`) :
    - metrics.json : valeurs brutes versionnables
    - metrics.md   : livrable jury
    - metrics/confusion_matrix.png
    - metrics/latency_boxplot.png
    - metrics/iou_heatmap.png

Le script entraine un modele RF ephemere a chaque run -- aucun pre-requis,
commande unique, totalement reproductible via le seed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.eval_metrics import run_evaluation  # noqa: E402
from app.services.exercise_catalog import Exercise, get_all  # noqa: E402

DEFAULT_N_PROFILES = 100
DEFAULT_SEED = 42
DEFAULT_OUT = Path("docs")


def _build_synthetic_catalog(size: int) -> list[Exercise]:
    """Catalogue de reference (sans dependance PG) -- pour reproductibilite offline."""
    categories = ["cardio", "strength", "flexibility"]
    difficulties = ["beginner", "intermediate", "advanced"]
    equipments = [
        ["none"],
        ["dumbbells"],
        ["barbell", "rack"],
        ["kettlebell"],
        ["resistance_band"],
        ["bench"],
        ["pull_up_bar"],
    ]
    muscles = [
        ["chest"],
        ["quadriceps", "glutes"],
        ["back", "biceps"],
        ["shoulders", "triceps"],
        ["calves"],
        ["abs"],
        ["lower_back"],
        ["hamstrings"],
    ]
    return [
        Exercise(
            id=i,
            name=f"exercice-{i}",
            target_muscles=muscles[i % len(muscles)],
            equipment=equipments[i % len(equipments)],
            difficulty=difficulties[i % len(difficulties)],
            category=categories[i % len(categories)],
        )
        for i in range(1, size + 1)
    ]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-profiles", type=int, default=DEFAULT_N_PROFILES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--synthetic",
        type=int,
        default=None,
        metavar="SIZE",
        help="Utiliser un catalogue synthetique de SIZE exercices (au lieu de PostgreSQL).",
    )
    return parser.parse_args(argv)


def _print_summary(report) -> None:
    print(f"Classifier F1            : {report.classifier_f1:.3f} (cible > 0.8)")
    print(
        f"Violations contraintes   : {report.constraint_violation_rate * 100:.1f} % "
        "(cible 0 %)"
    )
    print("Couverture par objectif  :")
    for goal, value in sorted(report.goal_coverage.items()):
        print(f"  {goal:<18s} {value * 100:.1f} %  (cible > 80 %)")
    print(f"Diversite (Jaccard)      : {report.diversity_jaccard:.3f} (cible < 0.5)")
    print(f"IoU rule-based vs ML     : {report.iou_rule_vs_ml:.3f} (cible 0.6-0.8)")
    print(
        f"Latence                  : p50={report.latency_p50_ms:.1f} ms "
        f"(cible < 200) / p95={report.latency_p95_ms:.1f} ms (cible < 500)"
    )
    print("HITL                     : a remplir manuellement (cible > 3.8/5)")


def _load_catalog(args: argparse.Namespace) -> list[Exercise]:
    if args.synthetic is not None:
        print(f"Using synthetic catalog ({args.synthetic} exercises).")
        return _build_synthetic_catalog(args.synthetic)
    db = SessionLocal()
    try:
        return get_all(db)
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    catalog = _load_catalog(args)
    if not catalog:
        print(
            "Catalogue d'exercices vide -- impossible d'evaluer le moteur.",
            file=sys.stderr,
        )
        return 1

    print(f"Loaded {len(catalog)} exercises from catalog.")
    print(
        f"Running evaluation : n_profiles={args.n_profiles}, "
        f"seed={args.seed}, out={args.out}/ ..."
    )
    report = run_evaluation(
        catalog=catalog,
        n_profiles=args.n_profiles,
        output_dir=args.out,
        seed=args.seed,
    )
    print(f"metrics.json -> {args.out / 'metrics.json'}")
    print(f"metrics.md   -> {args.out / 'metrics.md'}")
    print(f"PNGs         -> {args.out / 'metrics'}/")
    _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
