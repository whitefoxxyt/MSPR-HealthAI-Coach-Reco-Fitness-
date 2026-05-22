"""Tests for synthetic training dataset generation."""
from collections import Counter
from pathlib import Path

import pandas as pd
from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services.exercise_catalog import Exercise
from app.services.training_data import (
    Vocab,
    build_dataset,
    derive_vocab,
    describe_dataset,
    encode_pair,
    generate_profiles,
    write_dataset,
)


def _ex(
    exercise_id: int = 1,
    target_muscles: list[str] | None = None,
    equipment: list[str] | None = None,
    difficulty: str = "beginner",
    category: str | None = "strength",
) -> Exercise:
    return Exercise(
        id=exercise_id,
        name=f"ex-{exercise_id}",
        target_muscles=target_muscles or ["quadriceps"],
        equipment=equipment or ["none"],
        difficulty=difficulty,
        category=category,
    )


class TestDeriveVocab:
    def test_vocab_extracts_sorted_union_from_catalog(self):
        catalog = [
            _ex(1, target_muscles=["quadriceps", "glutes"], equipment=["barbell"]),
            _ex(
                2,
                target_muscles=["chest", "quadriceps"],
                equipment=["dumbbells"],
                category="cardio",
            ),
            _ex(3, target_muscles=["chest"], equipment=["none"], difficulty="advanced"),
        ]
        vocab = derive_vocab(catalog)
        assert vocab.muscles == ["chest", "glutes", "quadriceps"]
        assert vocab.equipment == ["barbell", "dumbbells"]
        assert vocab.categories == ["cardio", "strength"]
        assert vocab.difficulties == ["advanced", "beginner"]

    def test_vocab_excludes_none_equipment_token(self):
        catalog = [_ex(1, equipment=["none"])]
        vocab = derive_vocab(catalog)
        assert "none" not in vocab.equipment

    def test_vocab_excludes_null_category(self):
        catalog = [_ex(1, category=None), _ex(2, category="strength")]
        vocab = derive_vocab(catalog)
        assert vocab.categories == ["strength"]


def _full_vocab() -> Vocab:
    return Vocab(
        muscles=["chest", "glutes", "knee", "lower_back", "quadriceps"],
        equipment=["barbell", "dumbbells", "rack"],
        categories=["cardio", "strength"],
        difficulties=["beginner", "intermediate", "advanced"],
    )


class TestGenerateProfiles:
    def test_each_health_goal_gets_quarter_of_profiles(self):
        profiles = generate_profiles(n_profiles=100, vocab=_full_vocab(), seed=42)
        goals = Counter(p.health_goal_fitness for p in profiles)
        for goal in HealthGoalFitness:
            assert goals[goal] == 25

    def test_experience_levels_are_balanced_within_5_percent(self):
        profiles = generate_profiles(n_profiles=300, vocab=_full_vocab(), seed=42)
        levels = Counter(p.experience_level for p in profiles)
        expected = 100
        for level in ExperienceLevel:
            assert abs(levels[level] - expected) <= 15

    def test_seed_makes_output_deterministic(self):
        a = generate_profiles(n_profiles=50, vocab=_full_vocab(), seed=7)
        b = generate_profiles(n_profiles=50, vocab=_full_vocab(), seed=7)
        assert [p.model_dump() for p in a] == [p.model_dump() for p in b]

    def test_different_seeds_produce_different_profiles(self):
        a = generate_profiles(n_profiles=50, vocab=_full_vocab(), seed=1)
        b = generate_profiles(n_profiles=50, vocab=_full_vocab(), seed=2)
        assert [p.model_dump() for p in a] != [p.model_dump() for p in b]

    def test_equipment_and_limitations_are_subsets_of_vocab(self):
        vocab = _full_vocab()
        profiles = generate_profiles(n_profiles=40, vocab=vocab, seed=42)
        allowed_equipment = set(vocab.equipment)
        allowed_limitations = set(vocab.muscles) | set(vocab.categories)
        for p in profiles:
            assert set(p.equipment).issubset(allowed_equipment)
            assert set(p.limitations).issubset(allowed_limitations)

    def test_generated_profiles_show_diversity_in_equipment_lists(self):
        profiles = generate_profiles(n_profiles=200, vocab=_full_vocab(), seed=42)
        unique_equipment_sets = {tuple(sorted(p.equipment)) for p in profiles}
        assert len(unique_equipment_sets) >= 4


def _profile(
    health_goal_fitness: HealthGoalFitness = HealthGoalFitness.fat_loss,
    experience_level: ExperienceLevel = ExperienceLevel.intermediate,
    equipment: list[str] | None = None,
    limitations: list[str] | None = None,
) -> FitnessProfileRequest:
    return FitnessProfileRequest(
        health_goal_fitness=health_goal_fitness,
        experience_level=experience_level,
        equipment=equipment or [],
        limitations=limitations or [],
        preferences=SessionPreferences(),
    )


class TestEncodePair:
    def test_label_is_the_score(self):
        ex = _ex(1, target_muscles=["chest"], equipment=["dumbbells"], category="strength")
        vocab = derive_vocab([ex])
        row = encode_pair(ex, _profile(), score=0.42, vocab=vocab)
        assert row["label"] == 0.42

    def test_exercise_muscles_one_hot_uses_vocab_columns(self):
        catalog = [
            _ex(1, target_muscles=["chest"]),
            _ex(2, target_muscles=["quadriceps"]),
        ]
        vocab = derive_vocab(catalog)
        row = encode_pair(catalog[0], _profile(), score=0.0, vocab=vocab)
        assert row["ex_muscle_chest"] == 1
        assert row["ex_muscle_quadriceps"] == 0

    def test_profile_goal_one_hot_only_one_active(self):
        ex = _ex(1, target_muscles=["chest"])
        vocab = derive_vocab([ex])
        profile = _profile(health_goal_fitness=HealthGoalFitness.endurance)
        row = encode_pair(ex, profile, score=0.0, vocab=vocab)
        assert row["profile_goal_endurance"] == 1
        assert row["profile_goal_fat_loss"] == 0
        assert row["profile_goal_muscle_strength"] == 0
        assert row["profile_goal_general_health"] == 0

    def test_profile_equipment_multi_hot(self):
        catalog = [_ex(1, equipment=["barbell"]), _ex(2, equipment=["dumbbells"])]
        vocab = derive_vocab(catalog)
        profile = _profile(equipment=["barbell"])
        row = encode_pair(catalog[0], profile, score=0.0, vocab=vocab)
        assert row["profile_equipment_barbell"] == 1
        assert row["profile_equipment_dumbbells"] == 0

    def test_profile_limitations_multi_hot_covers_muscles_and_categories(self):
        catalog = [_ex(1, target_muscles=["lower_back"], category="cardio")]
        vocab = derive_vocab(catalog)
        profile = _profile(limitations=["lower_back", "cardio"])
        row = encode_pair(catalog[0], profile, score=0.0, vocab=vocab)
        assert row["profile_limit_lower_back"] == 1
        assert row["profile_limit_cardio"] == 1

    def test_exercise_difficulty_one_hot(self):
        catalog = [_ex(1, difficulty="beginner"), _ex(2, difficulty="advanced")]
        vocab = derive_vocab(catalog)
        row = encode_pair(catalog[1], _profile(), score=0.0, vocab=vocab)
        assert row["ex_difficulty_advanced"] == 1
        assert row["ex_difficulty_beginner"] == 0


def _mini_catalog(n: int = 10) -> list[Exercise]:
    """Genere n exercices varies couvrant cardio/strength, plusieurs niveaux et equipements."""
    categories = ["cardio", "strength"]
    difficulties = ["beginner", "intermediate", "advanced"]
    equipments = [["none"], ["dumbbells"], ["barbell", "rack"]]
    muscles = [["chest"], ["quadriceps"], ["glutes"], ["lower_back"]]
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


class TestBuildDataset:
    def test_dataset_size_equals_catalog_times_profiles(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=12, seed=42)
        assert len(df) == 10 * 12

    def test_label_in_unit_interval(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=12, seed=42)
        assert (df["label"] >= 0.0).all()
        assert (df["label"] <= 1.0).all()

    def test_dataset_has_label_column_and_one_hot_columns(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=8, seed=42)
        assert "label" in df.columns
        assert "exercise_id" in df.columns
        assert any(c.startswith("ex_muscle_") for c in df.columns)
        assert any(c.startswith("profile_goal_") for c in df.columns)

    def test_seed_makes_dataset_deterministic(self):
        catalog = _mini_catalog(10)
        a = build_dataset(catalog, n_profiles=8, seed=7)
        b = build_dataset(catalog, n_profiles=8, seed=7)
        assert a.equals(b)

    def test_changing_seed_changes_dataset(self):
        catalog = _mini_catalog(10)
        a = build_dataset(catalog, n_profiles=8, seed=1)
        b = build_dataset(catalog, n_profiles=8, seed=2)
        assert not a.equals(b)

    def test_dataset_reaches_acceptance_threshold(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=500, seed=42)
        assert len(df) >= 5000


class TestDescribeDataset:
    def test_describe_reports_row_count_and_label_stats(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=8, seed=42)
        stats = describe_dataset(df)
        assert stats["n_rows"] == 80
        assert 0.0 <= stats["label_mean"] <= 1.0
        assert 0.0 <= stats["label_std"] <= 1.0
        assert stats["label_min"] >= 0.0
        assert stats["label_max"] <= 1.0

    def test_describe_includes_distribution_per_goal(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=8, seed=42)
        stats = describe_dataset(df)
        assert "rows_per_goal" in stats
        goal_counts = stats["rows_per_goal"]
        assert sum(goal_counts.values()) == 80
        for goal in ("fat_loss", "muscle_strength", "endurance", "general_health"):
            assert goal in goal_counts

    def test_describe_includes_distribution_per_level(self):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=12, seed=42)
        stats = describe_dataset(df)
        assert "rows_per_level" in stats
        level_counts = stats["rows_per_level"]
        assert sum(level_counts.values()) == 120


class TestE2EMiniCatalog:
    """Critere d'acceptance issue 21 : 10 exos in -> fichier CSV valide out."""

    def test_mini_catalog_produces_valid_csv_file(self, tmp_path: Path):
        catalog = _mini_catalog(10)
        df = build_dataset(catalog, n_profiles=10, seed=42)
        output_path = tmp_path / "scoring_dataset.csv"

        write_dataset(df, output_path)

        assert output_path.exists()
        reloaded = pd.read_csv(output_path)
        assert len(reloaded) == 100
        assert "label" in reloaded.columns
        assert (reloaded["label"] >= 0.0).all()
        assert (reloaded["label"] <= 1.0).all()

    def test_write_creates_parent_directory_if_missing(self, tmp_path: Path):
        catalog = _mini_catalog(5)
        df = build_dataset(catalog, n_profiles=4, seed=42)
        output_path = tmp_path / "nested" / "training" / "dataset.csv"

        write_dataset(df, output_path)

        assert output_path.exists()
