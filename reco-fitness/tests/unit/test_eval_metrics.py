"""Tests unitaires des metriques d'evaluation (RF-14)."""
from __future__ import annotations

import pytest
from app.schemas.fitness_profile import (
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services import eval_metrics
from app.services.exercise_catalog import Exercise
from app.services.workout_program_orchestrator import WorkoutProgram


def _ex(
    exercise_id: int,
    *,
    target_muscles: list[str] | None = None,
    equipment: list[str] | None = None,
    difficulty: str = "intermediate",
    category: str | None = "strength",
) -> Exercise:
    return Exercise(
        id=exercise_id,
        name=f"ex-{exercise_id}",
        target_muscles=target_muscles or ["chest"],
        equipment=equipment or ["none"],
        difficulty=difficulty,
        category=category,
    )


def _program(exercises: list[Exercise], strategy: str = "rule_based") -> WorkoutProgram:
    return WorkoutProgram(
        weeks=[[exercises]],
        duration_weeks=1,
        scoring_strategy=strategy,  # type: ignore[arg-type]
    )


def _profile(
    *,
    health_goal: HealthGoalFitness = HealthGoalFitness.muscle_strength,
    experience: ExperienceLevel = ExperienceLevel.intermediate,
    equipment: list[str] | None = None,
    limitations: list[str] | None = None,
) -> FitnessProfileRequest:
    return FitnessProfileRequest(
        health_goal_fitness=health_goal,
        experience_level=experience,
        equipment=equipment or [],
        limitations=limitations or [],
        preferences=SessionPreferences(),
    )


class TestJaccardSimilarity:
    def test_identical_sets_returns_one(self):
        assert eval_metrics.jaccard_similarity({1, 2, 3}, {1, 2, 3}) == 1.0

    def test_disjoint_sets_returns_zero(self):
        assert eval_metrics.jaccard_similarity({1, 2}, {3, 4}) == 0.0

    def test_partial_overlap_returns_intersection_over_union(self):
        # |A inter B| = 1 ({2}); |A union B| = 3 ({1,2,3})
        assert eval_metrics.jaccard_similarity({1, 2}, {2, 3}) == pytest.approx(1 / 3)

    def test_two_empty_sets_returns_one_by_convention(self):
        # 0/0 indefinite -> on convient 1.0 (deux ensembles vides sont "identiques").
        assert eval_metrics.jaccard_similarity(set(), set()) == 1.0


class TestIoUTopK:
    def test_identical_top_k_returns_one(self):
        ranking = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assert eval_metrics.iou_top_k(ranking, ranking, k=10) == 1.0

    def test_disjoint_top_k_returns_zero(self):
        a = [1, 2, 3, 4, 5]
        b = [6, 7, 8, 9, 10]
        assert eval_metrics.iou_top_k(a, b, k=5) == 0.0

    def test_overlap_uses_top_k_only(self):
        # Top-3 : A={1,2,3}, B={2,3,4}; inter=2, union=4 -> 0.5
        a = [1, 2, 3, 99]
        b = [2, 3, 4, 88]
        assert eval_metrics.iou_top_k(a, b, k=3) == pytest.approx(0.5)

    def test_k_larger_than_ranking_uses_full_lists(self):
        # k=10 mais listes plus courtes -> equivalent a Jaccard sur listes completes.
        a = [1, 2]
        b = [2, 3]
        assert eval_metrics.iou_top_k(a, b, k=10) == pytest.approx(1 / 3)


class TestLatencyPercentiles:
    def test_uniform_distribution_p50_is_median(self):
        durations = [float(x) for x in range(1, 101)]  # 1..100
        p50, p95 = eval_metrics.latency_percentiles(durations)
        # p50 = mediane d'une suite 1..100 = (50 + 51) / 2 = 50.5
        assert p50 == pytest.approx(50.5)
        # p95 = quantile a 95% sur 100 valeurs (1..100) ~ 95.05
        assert p95 == pytest.approx(95.05, abs=0.5)

    def test_constant_durations_yields_same_value_for_p50_and_p95(self):
        durations = [42.0] * 100
        p50, p95 = eval_metrics.latency_percentiles(durations)
        assert p50 == pytest.approx(42.0)
        assert p95 == pytest.approx(42.0)

    def test_empty_durations_raises(self):
        with pytest.raises(ValueError):
            eval_metrics.latency_percentiles([])


class TestConstraintViolationRate:
    def test_all_programs_compliant_returns_zero(self):
        profile = _profile(equipment=["dumbbells"], limitations=["lower_back"])
        program = _program([_ex(1, equipment=["dumbbells"], target_muscles=["chest"])])
        assert eval_metrics.constraint_violation_rate([(program, profile)]) == 0.0

    def test_missing_equipment_counts_as_violation(self):
        profile = _profile(equipment=["dumbbells"])
        # exercice requiert barbell -- pas possede -> violation
        program = _program([_ex(1, equipment=["barbell"])])
        assert eval_metrics.constraint_violation_rate([(program, profile)]) == 1.0

    def test_limitation_match_counts_as_violation(self):
        profile = _profile(equipment=[], limitations=["lower_back"])
        program = _program([_ex(1, target_muscles=["lower_back"], equipment=["none"])])
        assert eval_metrics.constraint_violation_rate([(program, profile)]) == 1.0

    def test_half_of_programs_have_violations(self):
        profile = _profile(equipment=["dumbbells"])
        ok = _program([_ex(1, equipment=["dumbbells"])])
        bad = _program([_ex(2, equipment=["barbell"])])
        assert eval_metrics.constraint_violation_rate(
            [(ok, profile), (bad, profile)]
        ) == 0.5

    def test_no_programs_returns_zero(self):
        assert eval_metrics.constraint_violation_rate([]) == 0.0


class TestGoalCoverage:
    def test_full_coverage_when_all_appropriate_in_programs(self):
        programs_by_goal = {
            HealthGoalFitness.fat_loss: [_program([_ex(1), _ex(2)])],
        }
        appropriate_by_goal = {
            HealthGoalFitness.fat_loss: {1, 2},
        }
        coverage = eval_metrics.goal_coverage(programs_by_goal, appropriate_by_goal)
        assert coverage[HealthGoalFitness.fat_loss.value] == pytest.approx(1.0)

    def test_zero_coverage_when_none_appropriate_in_programs(self):
        programs_by_goal = {
            HealthGoalFitness.fat_loss: [_program([_ex(99)])],
        }
        appropriate_by_goal = {
            HealthGoalFitness.fat_loss: {1, 2},
        }
        coverage = eval_metrics.goal_coverage(programs_by_goal, appropriate_by_goal)
        assert coverage[HealthGoalFitness.fat_loss.value] == pytest.approx(0.0)

    def test_partial_coverage_returns_ratio(self):
        # 1 of 2 appropriate ids appears in programs
        programs_by_goal = {
            HealthGoalFitness.fat_loss: [_program([_ex(1)])],
        }
        appropriate_by_goal = {
            HealthGoalFitness.fat_loss: {1, 2},
        }
        coverage = eval_metrics.goal_coverage(programs_by_goal, appropriate_by_goal)
        assert coverage[HealthGoalFitness.fat_loss.value] == pytest.approx(0.5)

    def test_empty_appropriate_returns_one_by_convention(self):
        programs_by_goal = {
            HealthGoalFitness.fat_loss: [_program([_ex(1)])],
        }
        appropriate_by_goal = {
            HealthGoalFitness.fat_loss: set(),
        }
        coverage = eval_metrics.goal_coverage(programs_by_goal, appropriate_by_goal)
        # Rien a couvrir -> 1.0 (convention coherente avec Jaccard).
        assert coverage[HealthGoalFitness.fat_loss.value] == pytest.approx(1.0)

    def test_multi_goal_returns_one_entry_per_goal(self):
        programs_by_goal = {
            HealthGoalFitness.fat_loss: [_program([_ex(1)])],
            HealthGoalFitness.endurance: [_program([_ex(10), _ex(11)])],
        }
        appropriate_by_goal = {
            HealthGoalFitness.fat_loss: {1, 2},
            HealthGoalFitness.endurance: {10, 11},
        }
        coverage = eval_metrics.goal_coverage(programs_by_goal, appropriate_by_goal)
        assert coverage == {
            HealthGoalFitness.fat_loss.value: pytest.approx(0.5),
            HealthGoalFitness.endurance.value: pytest.approx(1.0),
        }


class TestF1Classifier:
    def test_perfect_predictions_yield_f1_one(self):
        y_true = [0.9, 0.8, 0.1, 0.2]
        y_pred = [0.9, 0.8, 0.1, 0.2]
        f1, cm = eval_metrics.f1_classifier(y_true, y_pred, threshold=0.5)
        assert f1 == pytest.approx(1.0)
        assert cm == {"tp": 2, "fp": 0, "fn": 0, "tn": 2}

    def test_all_wrong_predictions_yield_f1_zero(self):
        y_true = [0.9, 0.8, 0.1, 0.2]  # 2 positifs
        y_pred = [0.1, 0.2, 0.9, 0.8]  # tous inverses
        f1, cm = eval_metrics.f1_classifier(y_true, y_pred, threshold=0.5)
        assert f1 == pytest.approx(0.0)
        assert cm == {"tp": 0, "fp": 2, "fn": 2, "tn": 0}

    def test_mixed_predictions(self):
        # 3 positifs (>0.5), 2 negatifs. 2 TP, 1 FN, 1 FP, 1 TN.
        y_true = [0.9, 0.8, 0.7, 0.2, 0.1]
        y_pred = [0.9, 0.8, 0.3, 0.6, 0.1]
        f1, cm = eval_metrics.f1_classifier(y_true, y_pred, threshold=0.5)
        # precision = 2 / (2+1) = 0.6667, rappel = 2 / (2+1) = 0.6667 -> f1 ~= 0.6667
        assert f1 == pytest.approx(2 / 3, abs=1e-3)
        assert cm == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}


def _sample_report() -> "eval_metrics.EvaluationReport":
    return eval_metrics.EvaluationReport(
        classifier_f1=0.85,
        confusion_matrix={"tp": 40, "fp": 5, "fn": 5, "tn": 50},
        constraint_violation_rate=0.0,
        goal_coverage={
            "fat_loss": 0.85,
            "muscle_strength": 0.90,
            "endurance": 0.83,
            "general_health": 0.88,
        },
        diversity_jaccard=0.42,
        iou_rule_vs_ml=0.7,
        latency_p50_ms=150.0,
        latency_p95_ms=400.0,
        n_programs=100,
        seed=42,
        catalog_size=42,
        hitl_methodology="20 programmes notes 1-5 par 2 evaluateurs independants.",
        hitl_target_mean=3.8,
    )


class TestRenderJson:
    def test_json_contains_all_expected_keys(self):
        data = eval_metrics.render_metrics_json(_sample_report())
        expected = {
            "classifier_f1",
            "confusion_matrix",
            "constraint_violation_rate",
            "goal_coverage",
            "diversity_jaccard",
            "iou_rule_vs_ml",
            "latency_p50_ms",
            "latency_p95_ms",
            "n_programs",
            "seed",
            "catalog_size",
            "hitl_methodology",
            "hitl_target_mean",
        }
        assert set(data.keys()) == expected

    def test_json_values_reflect_report(self):
        data = eval_metrics.render_metrics_json(_sample_report())
        assert data["classifier_f1"] == pytest.approx(0.85)
        assert data["confusion_matrix"] == {"tp": 40, "fp": 5, "fn": 5, "tn": 50}
        assert data["goal_coverage"]["fat_loss"] == pytest.approx(0.85)


class TestRenderMarkdown:
    def test_markdown_contains_required_sections(self):
        md = eval_metrics.render_metrics_markdown(_sample_report())
        for header in (
            "## Statut des cibles PRD",
            "## Classifier",
            "## Contraintes dures",
            "## Couverture des objectifs",
            "## Diversite",
            "## IoU rule-based vs ML",
            "## Latence",
            "## Evaluation humaine (HITL)",
        ):
            assert header in md, f"section absente : {header!r}"

    def test_markdown_includes_metric_values(self):
        md = eval_metrics.render_metrics_markdown(_sample_report())
        # On verifie que les chiffres principaux apparaissent (formatage libre).
        assert "0.85" in md
        assert "0.42" in md
        assert "150" in md  # p50
        assert "400" in md  # p95
        assert "100" in md  # n_programs

    def test_markdown_summary_table_marks_passing_metrics_ok(self):
        # _sample_report() est calibre pour tout reussir.
        md = eval_metrics.render_metrics_markdown(_sample_report())
        assert "| OK |" in md
        assert "| a optimiser |" not in md

    def test_markdown_summary_marks_failures_as_to_optimize(self):
        bad_report = eval_metrics.EvaluationReport(
            classifier_f1=0.5,  # < 0.8
            confusion_matrix={"tp": 0, "fp": 1, "fn": 1, "tn": 0},
            constraint_violation_rate=0.1,  # > 0
            goal_coverage={"fat_loss": 0.5},  # < 0.8
            diversity_jaccard=0.9,  # > 0.5
            iou_rule_vs_ml=0.2,  # < 0.6
            latency_p50_ms=900.0,  # > 200
            latency_p95_ms=1500.0,  # > 500
            n_programs=10,
            seed=1,
            catalog_size=10,
            hitl_methodology="...",
        )
        md = eval_metrics.render_metrics_markdown(bad_report)
        assert "| a optimiser |" in md
        assert "| OK |" not in md


def _is_png(path) -> bool:
    return path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


class TestPlotConfusionMatrix:
    def test_writes_png_to_path(self, tmp_path):
        out = tmp_path / "cm.png"
        eval_metrics.plot_confusion_matrix(
            {"tp": 40, "fp": 5, "fn": 5, "tn": 50}, out
        )
        assert out.exists()
        assert _is_png(out)


class TestPlotLatencyBoxplot:
    def test_writes_png_to_path(self, tmp_path):
        out = tmp_path / "lat.png"
        eval_metrics.plot_latency_boxplot([100.0, 120.0, 130.0, 200.0, 350.0], out)
        assert out.exists()
        assert _is_png(out)


class TestPlotIouHeatmap:
    def test_writes_png_to_path(self, tmp_path):
        out = tmp_path / "iou.png"
        labels = ["fat_loss", "muscle_strength"]
        matrix = [[1.0, 0.6], [0.6, 1.0]]
        eval_metrics.plot_iou_heatmap(matrix, labels, out)
        assert out.exists()
        assert _is_png(out)


class TestTopKIds:
    def test_returns_ids_sorted_by_descending_score(self):
        assert eval_metrics._top_k_ids({1: 0.2, 2: 0.9, 3: 0.5}, k=2) == [2, 3]

    def test_k_larger_than_input_returns_all(self):
        assert eval_metrics._top_k_ids({1: 0.5}, k=10) == [1]


class TestExerciseIdsInProgram:
    def test_collects_unique_ids_across_weeks_and_sessions(self):
        program = WorkoutProgram(
            weeks=[
                [[_ex(1), _ex(2)], [_ex(2), _ex(3)]],
                [[_ex(3), _ex(4)]],
            ],
            duration_weeks=2,
            scoring_strategy="rule_based",
        )
        assert eval_metrics._exercise_ids_in_program(program) == {1, 2, 3, 4}


class TestAppropriateByGoal:
    def test_returns_one_entry_per_health_goal(self):
        catalog = [
            _ex(1, category="cardio", target_muscles=["chest"]),
            _ex(2, category="strength", target_muscles=["quadriceps"]),
            _ex(3, category="flexibility", target_muscles=["abs"]),
        ]
        result = eval_metrics._appropriate_by_goal(catalog)
        assert set(result.keys()) == set(HealthGoalFitness)
        for ids in result.values():
            assert ids.issubset({1, 2, 3})


class TestMlIouMatrix:
    def test_iou_one_when_ml_matches_rule_based(self, monkeypatch):
        # Patch scoring_ml pour qu'il renvoie exactement le rule-based -> top-10 identiques.
        from app.services import scoring_ml as ml_module
        from app.services import scoring_rule_based

        monkeypatch.setattr(
            ml_module,
            "score_exercise",
            lambda ex, profile: scoring_rule_based.score_exercise(ex, profile, []),
        )
        catalog = [_ex(i, category="strength") for i in range(1, 6)]
        profiles = [_profile()]
        mean_iou, matrix = eval_metrics._ml_iou_matrix(profiles, catalog)
        assert mean_iou == pytest.approx(1.0)
        assert matrix == [[pytest.approx(1.0)]]


class TestDiversityMean:
    def test_perfect_diversity_returns_zero(self, monkeypatch):
        # On bypass l'orchestrator : 1er programme = {1,2,3}, 2eme = {4,5,6} -> Jaccard 0
        from app.services import eval_metrics as em

        produced: list[WorkoutProgram] = [
            WorkoutProgram(
                weeks=[[[_ex(1), _ex(2), _ex(3)]]],
                duration_weeks=1,
                scoring_strategy="hybrid_rank_fusion",
            ),
            WorkoutProgram(
                weeks=[[[_ex(4), _ex(5), _ex(6)]]],
                duration_weeks=1,
                scoring_strategy="hybrid_rank_fusion",
            ),
        ]
        calls = iter(produced)
        monkeypatch.setattr(em, "_generate_program", lambda *a, **kw: next(calls))
        result = em._diversity_mean([_profile()], catalog=[])
        assert result == pytest.approx(0.0)


class TestLatencyRun:
    def test_collects_one_duration_per_profile(self, monkeypatch):
        from app.services import eval_metrics as em

        program = WorkoutProgram(
            weeks=[[[_ex(1)]]],
            duration_weeks=1,
            scoring_strategy="hybrid_rank_fusion",
        )
        monkeypatch.setattr(em, "_generate_program", lambda *a, **kw: program)
        profiles = [_profile(), _profile()]
        durations, programs = em._latency_run(profiles, catalog=[])
        assert len(durations) == 2
        assert all(d >= 0.0 for d in durations)
        assert programs == [program, program]


class TestEvaluateClassifier:
    def test_returns_f1_and_confusion_dict_from_trained_model(self, tmp_path):
        from app.services.scoring_trainer import train_and_persist
        from app.services.training_data import build_dataset

        # Mini-catalogue suffisant pour build_dataset + train (~150 lignes).
        mini_catalog = [
            _ex(
                i,
                category=["cardio", "strength", "flexibility"][i % 3],
                difficulty=["beginner", "intermediate", "advanced"][i % 3],
                equipment=[["none"], ["dumbbells"]][i % 2],
                target_muscles=[["chest"], ["abs"]][i % 2],
            )
            for i in range(1, 7)
        ]
        df = build_dataset(mini_catalog, n_profiles=30, seed=42)
        csv_path = tmp_path / "ds.csv"
        df.to_csv(csv_path, index=False)
        model_path = tmp_path / "model.pkl"
        train_and_persist(csv_path, model_path, tmp_path / "report.json")

        f1, cm = eval_metrics._evaluate_classifier(csv_path, model_path)
        assert 0.0 <= f1 <= 1.0
        assert set(cm.keys()) == {"tp", "fp", "fn", "tn"}
        assert sum(cm.values()) > 0
