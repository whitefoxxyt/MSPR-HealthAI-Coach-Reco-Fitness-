"""Tests unitaires de l'orchestrateur de programmes d'entrainement (RF-10)."""
import pytest

from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services import workout_program_orchestrator as orchestrator
from app.services.exercise_catalog import Exercise


def _make_exercise(
    exercise_id: int,
    name: str = "ex",
    category: str = "cardio",
    difficulty: str = "beginner",
    equipment: list[str] | None = None,
    target_muscles: list[str] | None = None,
) -> Exercise:
    return Exercise(
        id=exercise_id,
        name=name,
        category=category,
        difficulty=difficulty,
        equipment=equipment if equipment is not None else ["none"],
        target_muscles=target_muscles if target_muscles is not None else ["quadriceps"],
    )


def _profile(
    goal: HealthGoalFitness = HealthGoalFitness.fat_loss,
    level: ExperienceLevel = ExperienceLevel.beginner,
    equipment: list[str] | None = None,
    limitations: list[str] | None = None,
) -> FitnessProfileRequest:
    return FitnessProfileRequest(
        health_goal_fitness=goal,
        experience_level=level,
        equipment=equipment if equipment is not None else [],
        limitations=limitations if limitations is not None else [],
        preferences=SessionPreferences(),
    )


class TestRecommendFree:
    def test_returns_program_with_two_weeks_and_rule_based_strategy(self):
        catalog = [
            _make_exercise(i, name=f"ex-{i}", category="cardio")
            for i in range(1, 25)
        ]
        profile = _profile(goal=HealthGoalFitness.fat_loss)

        program = orchestrator.recommend_free(profile, history=[], catalog=catalog)

        assert program.duration_weeks == 2
        assert program.scoring_strategy == "rule_based"
        assert len(program.weeks) == 2
        # fat_loss -> 4 seances/sem, 8 ex/seance (mapping module)
        for week in program.weeks:
            assert len(week) == 4
            for session in week:
                assert len(session) == 8
                for exercise in session:
                    assert isinstance(exercise, Exercise)

    def test_excludes_exercises_requiring_missing_equipment(self):
        # 30 ex requierent un barbell (user n'en a pas), 30 sont au poids du corps.
        # Filtre dur post-scoring : aucun barbell dans le programme.
        barbell_only = [
            _make_exercise(i, name=f"barbell-{i}", equipment=["barbell"])
            for i in range(1, 31)
        ]
        bodyweight = [
            _make_exercise(i + 100, name=f"body-{i}", equipment=["none"])
            for i in range(1, 31)
        ]
        profile = _profile(equipment=["dumbbells"])  # pas de barbell

        program = orchestrator.recommend_free(
            profile, history=[], catalog=barbell_only + bodyweight
        )

        all_exercises = [ex for week in program.weeks for session in week for ex in session]
        forbidden_ids = {ex.id for ex in barbell_only}
        chosen_ids = {ex.id for ex in all_exercises}
        assert chosen_ids.isdisjoint(forbidden_ids), (
            f"exercices avec equipement absent presents : {chosen_ids & forbidden_ids}"
        )

    def test_excludes_exercises_targeting_a_limitation(self):
        # 30 exercices ciblent un muscle limite par le user, 30 sont OK.
        # Sans filtre dur, certains exercices "knee" pourraient slipper si le score
        # rule-based reste positif. Le filtre dur post-scoring doit les exclure.
        bad = [
            _make_exercise(i, name=f"knee-{i}", target_muscles=["knees"])
            for i in range(1, 31)
        ]
        good = [
            _make_exercise(i + 100, name=f"ok-{i}", target_muscles=["abs"])
            for i in range(1, 31)
        ]
        profile = _profile(limitations=["knees"])

        program = orchestrator.recommend_free(profile, history=[], catalog=bad + good)

        all_exercises = [ex for week in program.weeks for session in week for ex in session]
        bad_ids = {ex.id for ex in bad}
        chosen_ids = {ex.id for ex in all_exercises}
        assert chosen_ids.isdisjoint(bad_ids), (
            f"exercices contre-indiques presents dans le programme : {chosen_ids & bad_ids}"
        )


class TestRecommendPremium:
    @pytest.fixture(autouse=True)
    def _stub_ml(self, monkeypatch):
        """Stub scoring_ml : score deterministe pour rendre la fusion testable."""
        def fake_ml(exercise, profile):
            # score deterministe inverse de l'id : id=1 -> 0.99, id=2 -> 0.98, ...
            return max(0.0, 1.0 - exercise.id * 0.001)

        monkeypatch.setattr(
            "app.services.workout_program_orchestrator.score_ml",
            fake_ml,
        )

    def test_uses_hybrid_rank_fusion_and_full_duration(self):
        catalog = [
            _make_exercise(i, name=f"ex-{i}", category="strength", difficulty="intermediate")
            for i in range(1, 31)
        ]
        profile = _profile(
            goal=HealthGoalFitness.muscle_strength,
            level=ExperienceLevel.intermediate,
        )

        program = orchestrator.recommend_premium(profile, history=[], catalog=catalog)

        # muscle_strength : 6 semaines, 4 seances/sem, 6 ex/seance (mapping module)
        assert program.duration_weeks == 6
        assert program.scoring_strategy == "hybrid_rank_fusion"
        assert len(program.weeks) == 6
        for week in program.weeks:
            assert len(week) == 4
            for session in week:
                assert len(session) == 6

    def test_top_candidates_are_capped_at_twenty(self):
        # Catalogue de 100 ex. La fusion Top-N=20 ne doit selectionner que parmi
        # les 20 meilleurs de chaque strategie. On rend l'ex id=999 mauvais
        # pour rule-based et bon pour ML (ml score eleve, mais filtres
        # rule-based moyens) : il NE doit PAS apparaitre.
        catalog = [
            _make_exercise(i, name=f"ex-{i}", category="strength", difficulty="intermediate")
            for i in range(1, 101)
        ]
        # Cible : on ne verifie pas un id specifique mais que tous les ex
        # selectionnes sont issus du Top-20 de l'une des 2 listes.
        profile = _profile(
            goal=HealthGoalFitness.muscle_strength,
            level=ExperienceLevel.intermediate,
        )

        program = orchestrator.recommend_premium(profile, history=[], catalog=catalog)

        # Reconstitue les deux Top-20 utilises par la fusion
        from app.services.scoring_rule_based import score_exercise as rb
        from app.services.workout_program_orchestrator import score_ml

        top_rb = {
            ex.id for ex in sorted(catalog, key=lambda e: rb(e, profile, []), reverse=True)[:20]
        }
        top_ml = {
            ex.id for ex in sorted(catalog, key=lambda e: score_ml(e, profile), reverse=True)[:20]
        }
        union_top = top_rb | top_ml

        chosen_ids = {
            ex.id for week in program.weeks for session in week for ex in session
        }
        assert chosen_ids.issubset(union_top), (
            f"exercices hors Top-20 selectionnes : {chosen_ids - union_top}"
        )


class TestRecommendPremiumPlus:
    @pytest.fixture(autouse=True)
    def _stub_ml(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.workout_program_orchestrator.score_ml",
            lambda exercise, profile: max(0.0, 1.0 - exercise.id * 0.001),
        )

    def test_without_biometrics_uses_neutral_intensity(self):
        catalog = [
            _make_exercise(i, category="strength", difficulty="intermediate")
            for i in range(1, 31)
        ]
        profile = _profile(
            goal=HealthGoalFitness.muscle_strength,
            level=ExperienceLevel.intermediate,
        )

        program = orchestrator.recommend_premium_plus(
            profile, history=[], catalog=catalog, biometrics=None
        )

        assert program.scoring_strategy == "hybrid_rank_fusion"
        assert program.intensity_modifier == 1.0

    def test_high_resting_heart_rate_lowers_intensity(self):
        from datetime import datetime, timezone

        from app.services.biometric_reader import Biometrics

        catalog = [
            _make_exercise(i, category="strength", difficulty="intermediate")
            for i in range(1, 31)
        ]
        profile = _profile(
            goal=HealthGoalFitness.muscle_strength,
            level=ExperienceLevel.intermediate,
        )
        # HR repos eleve -> signal de fatigue/surentrainement, on baisse la charge
        biometrics = Biometrics(
            heart_rate_rest=90,
            bmi=24.0,
            body_fat_pct=18.0,
            recorded_at=datetime.now(timezone.utc),
        )

        program = orchestrator.recommend_premium_plus(
            profile, history=[], catalog=catalog, biometrics=biometrics
        )

        assert program.intensity_modifier < 1.0
