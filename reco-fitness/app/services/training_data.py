"""Generation de dataset synthetique pour entrainer le scoring ML."""
import random
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services.exercise_catalog import Exercise
from app.services.scoring_rule_based import score_exercise


@dataclass(frozen=True)
class Vocab:
    """Vocabulaire trie extrait du catalogue : alphabet stable pour encoder en one-hot."""

    muscles: list[str]
    equipment: list[str]
    categories: list[str]
    difficulties: list[str]


def derive_vocab(exercises: list[Exercise]) -> Vocab:
    """Extrait l'union triee des muscles, equipements, categories et difficultes du catalogue."""
    muscles: set[str] = set()
    equipment: set[str] = set()
    categories: set[str] = set()
    difficulties: set[str] = set()
    for ex in exercises:
        muscles.update(ex.target_muscles)
        equipment.update(item for item in ex.equipment if item != "none")
        if ex.category is not None:
            categories.add(ex.category)
        difficulties.add(ex.difficulty)
    return Vocab(
        muscles=sorted(muscles),
        equipment=sorted(equipment),
        categories=sorted(categories),
        difficulties=sorted(difficulties),
    )


_GOALS = list(HealthGoalFitness)
_LEVELS = list(ExperienceLevel)


def _sample_subset(rng: random.Random, pool: list[str], max_size: int) -> list[str]:
    """Tire un sous-ensemble de taille aleatoire dans [0, min(max_size, len(pool))]."""
    if not pool:
        return []
    size = rng.randint(0, min(max_size, len(pool)))
    return sorted(rng.sample(pool, size))


def generate_profiles(
    n_profiles: int,
    vocab: Vocab,
    seed: int,
) -> list[FitnessProfileRequest]:
    """Genere n profils stratifies : 1/4 par objectif sante, ~1/3 par niveau d'experience.

    Equipement et limitations sont des sous-ensembles aleatoires du vocab.
    Reproductible via le seed.
    """
    rng = random.Random(seed)
    limitations_pool = sorted(set(vocab.muscles) | set(vocab.categories))

    profiles: list[FitnessProfileRequest] = []
    for i in range(n_profiles):
        goal = _GOALS[i % len(_GOALS)]
        level = _LEVELS[(i // len(_GOALS)) % len(_LEVELS)]
        profiles.append(
            FitnessProfileRequest(
                health_goal_fitness=goal,
                experience_level=level,
                equipment=_sample_subset(rng, vocab.equipment, max_size=len(vocab.equipment)),
                limitations=_sample_subset(rng, limitations_pool, max_size=2),
                preferences=SessionPreferences(),
            )
        )

    rng.shuffle(profiles)
    return profiles


def _multi_hot(values: list[str], vocab_values: list[str], prefix: str) -> dict[str, int]:
    present = set(values)
    return {f"{prefix}_{v}": int(v in present) for v in vocab_values}


def _one_hot(value: str, vocab_values: list[str], prefix: str) -> dict[str, int]:
    return {f"{prefix}_{v}": int(value == v) for v in vocab_values}


def encode_pair(
    exercise: Exercise,
    profile: FitnessProfileRequest,
    score: float,
    vocab: Vocab,
) -> dict[str, float | int]:
    """Encode une paire (exercise, profile) en un dict plat de features + label numerique."""
    row: dict[str, float | int] = {"exercise_id": exercise.id}
    row.update(_multi_hot(exercise.target_muscles, vocab.muscles, "ex_muscle"))
    row.update(_multi_hot(exercise.equipment, vocab.equipment, "ex_equipment"))
    row.update(_one_hot(exercise.difficulty, vocab.difficulties, "ex_difficulty"))
    row.update(_one_hot(exercise.category or "", vocab.categories, "ex_category"))
    row.update(
        _one_hot(profile.health_goal_fitness.value, [g.value for g in _GOALS], "profile_goal")
    )
    row.update(
        _one_hot(
            profile.experience_level.value,
            [lv.value for lv in _LEVELS],
            "profile_level",
        )
    )
    row.update(_multi_hot(profile.equipment, vocab.equipment, "profile_equipment"))
    limitations_pool = sorted(set(vocab.muscles) | set(vocab.categories))
    row.update(_multi_hot(profile.limitations, limitations_pool, "profile_limit"))
    row["label"] = max(0.0, min(1.0, score))
    return row


def build_dataset(
    exercises: list[Exercise],
    n_profiles: int,
    seed: int,
) -> pd.DataFrame:
    """Produit un DataFrame cartesien (exercises x profiles) avec features encodees + label."""
    vocab = derive_vocab(exercises)
    profiles = generate_profiles(n_profiles=n_profiles, vocab=vocab, seed=seed)
    rows = [
        encode_pair(
            exercise,
            profile,
            score=score_exercise(exercise, profile, history=[]),
            vocab=vocab,
        )
        for profile in profiles
        for exercise in exercises
    ]
    return pd.DataFrame(rows)


def describe_dataset(df: pd.DataFrame) -> dict[str, object]:
    """Calcule des stats descriptives : taille, distribution label, balance par goal/level."""
    goal_cols = [c for c in df.columns if c.startswith("profile_goal_")]
    level_cols = [c for c in df.columns if c.startswith("profile_level_")]
    rows_per_goal = {c.removeprefix("profile_goal_"): int(df[c].sum()) for c in goal_cols}
    rows_per_level = {c.removeprefix("profile_level_"): int(df[c].sum()) for c in level_cols}
    return {
        "n_rows": int(len(df)),
        "label_mean": float(df["label"].mean()),
        "label_std": float(df["label"].std()),
        "label_min": float(df["label"].min()),
        "label_max": float(df["label"].max()),
        "rows_per_goal": rows_per_goal,
        "rows_per_level": rows_per_level,
    }


def write_dataset(df: pd.DataFrame, path: Path) -> None:
    """Ecrit le dataset au format CSV ; cree les dossiers parents si besoin."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
