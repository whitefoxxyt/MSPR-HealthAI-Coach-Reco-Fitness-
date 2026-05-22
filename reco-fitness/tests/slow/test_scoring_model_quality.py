"""Test de qualite du modele : F1 > 0.7 sur le jeu de test (PRD).

Lent (~30s) car on entraine un vrai RandomForest sur un dataset realiste.
Lancer avec : pytest -m slow
"""
import json
from pathlib import Path

import pytest
from app.services.exercise_catalog import Exercise
from app.services.scoring_trainer import train_and_persist
from app.services.training_data import build_dataset


def _realistic_catalog(n: int = 40) -> list[Exercise]:
    categories = ["cardio", "strength", "flexibility"]
    difficulties = ["beginner", "intermediate", "advanced"]
    equipments = [
        ["none"],
        ["dumbbells"],
        ["barbell", "rack"],
        ["kettlebell"],
        ["resistance_band"],
        ["bench"],
    ]
    muscles = [
        ["chest"],
        ["quadriceps", "glutes"],
        ["back", "biceps"],
        ["shoulders"],
        ["calves"],
        ["abs"],
        ["lower_back"],
        ["hamstrings"],
    ]
    return [
        Exercise(
            id=i,
            name=f"ex-{i}",
            target_muscles=muscles[i % len(muscles)],
            equipment=equipments[i % len(equipments)],
            difficulty=difficulties[i % len(difficulties)],
            category=categories[i % len(categories)],
        )
        for i in range(1, n + 1)
    ]


@pytest.mark.slow
def test_f1_exceeds_acceptance_threshold(tmp_path: Path):
    """Critere PRD : F1 > 0.7 sur la classification "score > 0.5"."""
    catalog = _realistic_catalog(40)
    df = build_dataset(catalog, n_profiles=150, seed=42)
    csv_path = tmp_path / "scoring_dataset.csv"
    df.to_csv(csv_path, index=False)

    model_path = tmp_path / "scoring_model.pkl"
    report_path = tmp_path / "training_report.json"
    train_and_persist(csv_path, model_path, report_path)

    report = json.loads(report_path.read_text())
    assert report["test"]["f1"] > 0.7, f"F1={report['test']['f1']:.3f} <= 0.7"
