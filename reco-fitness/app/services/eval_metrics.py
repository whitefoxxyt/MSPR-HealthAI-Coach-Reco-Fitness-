"""Metriques d'evaluation du moteur de recommandations (RF-14).

Fonctions pures + orchestrateur `run_evaluation` qui agrege les 7 metriques
exigees par le PRD (livrable IV) en `docs/metrics.json`, `docs/metrics.md`
et trois PNG sous `docs/metrics/`.
"""
from __future__ import annotations

import json
import statistics
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # noqa: E402 -- backend non-GUI obligatoire avant pyplot
import joblib  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import confusion_matrix, f1_score  # noqa: E402

from app.schemas.fitness_profile import (  # noqa: E402
    ExperienceLevel,
    FitnessProfileRequest,
    HealthGoalFitness,
    SessionPreferences,
)
from app.services import scoring_ml  # noqa: E402
from app.services.exercise_catalog import Exercise  # noqa: E402
from app.services.scoring_rule_based import (  # noqa: E402
    score_exercise as score_rule_based,
)
from app.services.scoring_trainer import split_60_20_20, train_and_persist  # noqa: E402
from app.services.training_data import (  # noqa: E402
    build_dataset,
    derive_vocab,
    generate_profiles,
    write_dataset,
)
from app.services.workout_program_orchestrator import (  # noqa: E402
    WorkoutProgram,
    passes_hard_filters,
    recommend_premium,
)


@dataclass
class EvaluationReport:
    """Agrege les 7 metriques du PRD (livrable IV) + meta-donnees de reproductibilite."""

    classifier_f1: float
    confusion_matrix: dict[str, int]
    constraint_violation_rate: float
    goal_coverage: dict[str, float]
    diversity_jaccard: float
    iou_rule_vs_ml: float
    latency_p50_ms: float
    latency_p95_ms: float
    n_programs: int
    seed: int
    catalog_size: int
    hitl_methodology: str
    hitl_target_mean: float = 3.8


def jaccard_similarity(a: set[int], b: set[int]) -> float:
    """Indice de Jaccard : |A inter B| / |A union B|. Deux vides -> 1.0 (convention)."""
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def iou_top_k(ranking_a: list[int], ranking_b: list[int], k: int) -> float:
    """IoU sur les top-k de deux rankings d'ids. Si k > len, prend la liste entiere."""
    return jaccard_similarity(set(ranking_a[:k]), set(ranking_b[:k]))


def latency_percentiles(durations_ms: list[float]) -> tuple[float, float]:
    """Retourne (p50, p95) sur une liste de latences (ms). Liste vide -> ValueError."""
    if not durations_ms:
        raise ValueError("latency_percentiles requires at least one duration")
    if len(durations_ms) == 1:
        return durations_ms[0], durations_ms[0]
    # quantiles(method="inclusive") rend p_i = i*(n-1)/100, coherent avec numpy.percentile.
    cuts = statistics.quantiles(durations_ms, n=100, method="inclusive")
    return cuts[49], cuts[94]


def _iter_program_exercises(program: WorkoutProgram):
    for week in program.weeks:
        for session in week:
            yield from session


def constraint_violation_rate(
    program_profile_pairs: list[tuple[WorkoutProgram, FitnessProfileRequest]],
) -> float:
    """Taux de programmes contenant au moins un exercice violant equipement ou limitation."""
    if not program_profile_pairs:
        return 0.0
    violating = sum(
        1
        for program, profile in program_profile_pairs
        if any(
            not passes_hard_filters(ex, profile)
            for ex in _iter_program_exercises(program)
        )
    )
    return violating / len(program_profile_pairs)


def f1_classifier(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    threshold: float = 0.5,
) -> tuple[float, dict[str, int]]:
    """F1 et matrice de confusion sur la binarisation `score > threshold`."""
    true_cls = (np.asarray(y_true) > threshold).astype(int)
    pred_cls = (np.asarray(y_pred) > threshold).astype(int)
    f1 = float(f1_score(true_cls, pred_cls, zero_division=0))
    tn, fp, fn, tp = confusion_matrix(true_cls, pred_cls, labels=[0, 1]).ravel()
    return f1, {"tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)}


def plot_confusion_matrix(cm: dict[str, int], path: Path) -> None:
    """Trace la matrice de confusion 2x2 en PNG (axes [0,1], annotations dans les cellules)."""
    matrix = [[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]]
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks([0, 1], labels=["Pred 0", "Pred 1"])
    ax.set_yticks([0, 1], labels=["True 0", "True 1"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(matrix[i][j]), ha="center", va="center", color="black")
    fig.colorbar(im, ax=ax)
    ax.set_title("Matrice de confusion (score > 0.5)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_latency_boxplot(durations_ms: Sequence[float], path: Path) -> None:
    """Trace la distribution des latences en PNG (boxplot horizontal)."""
    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.boxplot(durations_ms, orientation="horizontal", widths=0.6)
    ax.set_xlabel("Latence (ms)")
    ax.set_title(f"Distribution des latences (n={len(durations_ms)})")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_iou_heatmap(matrix: Sequence[Sequence[float]], labels: Sequence[str], path: Path) -> None:
    """Trace une heatmap IoU NxN (intra-objectif) en PNG."""
    arr = np.asarray(matrix)
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(arr, vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set_xticks(range(len(labels)), labels=labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels=labels)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, f"{arr[i, j]:.2f}", ha="center", va="center", color="white")
    fig.colorbar(im, ax=ax)
    ax.set_title("Heatmap IoU top-10 (rule-based vs ML)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def render_metrics_json(report: EvaluationReport) -> dict:
    """Serialise un `EvaluationReport` en dict pret pour `json.dump`."""
    return asdict(report)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f} %"


def _target_status(report: EvaluationReport) -> list[tuple[str, str, str, bool]]:
    """Construit la grille (nom, valeur, cible, pass) pour les 6 metriques auto."""
    coverage_values = list(report.goal_coverage.values())
    coverage_min = min(coverage_values) if coverage_values else 0.0
    return [
        (
            "F1 classifier",
            f"{report.classifier_f1:.3f}",
            "> 0.8",
            report.classifier_f1 > 0.8,
        ),
        (
            "Violation contraintes",
            _fmt_pct(report.constraint_violation_rate),
            "0 %",
            report.constraint_violation_rate == 0.0,
        ),
        (
            "Couverture min (par goal)",
            _fmt_pct(coverage_min),
            "> 80 %",
            coverage_min > 0.8,
        ),
        (
            "Diversite Jaccard",
            f"{report.diversity_jaccard:.3f}",
            "< 0.5",
            report.diversity_jaccard < 0.5,
        ),
        (
            "IoU rule-based vs ML",
            f"{report.iou_rule_vs_ml:.3f}",
            "0.6 - 0.8",
            0.6 <= report.iou_rule_vs_ml <= 0.8,
        ),
        (
            "Latence p50 / p95",
            f"{report.latency_p50_ms:.1f} / {report.latency_p95_ms:.1f} ms",
            "< 200 / < 500 ms",
            report.latency_p50_ms < 200 and report.latency_p95_ms < 500,
        ),
    ]


def render_metrics_markdown(report: EvaluationReport) -> str:
    """Rend un `EvaluationReport` en Markdown structure (sections du livrable jury)."""
    cm = report.confusion_matrix
    goal_lines = "\n".join(
        f"| {goal} | {_fmt_pct(value)} |"
        for goal, value in sorted(report.goal_coverage.items())
    )
    status_lines = "\n".join(
        f"| {name} | {value} | {target} | {'OK' if ok else 'a optimiser'} |"
        for name, value, target, ok in _target_status(report)
    )
    return f"""# Metriques d'evaluation -- moteur de recommandations fitness

> Reproduction : `python scripts/eval_metrics.py` (seed={report.seed}).
> Catalogue : {report.catalog_size} exercices, {report.n_programs} programmes generes.

## Statut des cibles PRD

| Metrique | Valeur | Cible | Statut |
|----------|--------|-------|--------|
{status_lines}

## Classifier

- **F1 (score > 0.5)** : {report.classifier_f1:.3f} -- cible > 0.8
- Matrice de confusion : TP={cm["tp"]} FP={cm["fp"]} FN={cm["fn"]} TN={cm["tn"]}

Voir `metrics/confusion_matrix.png`.

## Contraintes dures

- **Taux de violation** : {_fmt_pct(report.constraint_violation_rate)} -- cible 0 %
- Sur {report.n_programs} programmes generes, % contenant un exercice avec equipement absent
  OU contre-indique par une limitation.

## Couverture des objectifs

| Objectif | Couverture |
|----------|-----------|
{goal_lines}

Cible : > 80 % par objectif.

## Diversite

- **Jaccard moyen sur 2 programmes consecutifs** : {report.diversity_jaccard:.3f} -- cible < 0.5
- Plus l'indice est faible, plus les programmes sont varies.

## IoU rule-based vs ML

- **IoU top-10** : {report.iou_rule_vs_ml:.3f} -- cible 0.6 a 0.8
- Recouvrement des top-10 exercices entre les deux strategies (proximite des classements).

Voir `metrics/iou_heatmap.png`.

## Latence

- **p50** : {report.latency_p50_ms:.1f} ms -- cible < 200 ms
- **p95** : {report.latency_p95_ms:.1f} ms -- cible < 500 ms

Mesure sur {report.n_programs} appels in-process de `recommend_premium`.
Voir `metrics/latency_boxplot.png`.

## Evaluation humaine (HITL)

**Methodologie** : {report.hitl_methodology}

**Cible** : moyenne > {report.hitl_target_mean:.1f}/5.

| # | Programme (id) | Note (1-5) | Commentaire |
|---|----------------|------------|-------------|
| 1 | _a remplir_    | _._        | _._         |
| ...| ...           | ...        | ...         |
| 20 | _a remplir_   | _._        | _._         |

> Cette section est un livrable jury : les 20 notations sont a saisir manuellement
> apres tirage aleatoire de 20 programmes parmi ceux generes (voir `metrics.json`).
"""


def goal_coverage(
    programs_by_goal: dict[HealthGoalFitness, list[WorkoutProgram]],
    appropriate_by_goal: dict[HealthGoalFitness, set[int]],
) -> dict[str, float]:
    """Pour chaque goal : % des exercices "appropriate" presents dans les programmes generes."""
    coverage: dict[str, float] = {}
    for goal, programs in programs_by_goal.items():
        appropriate = appropriate_by_goal.get(goal, set())
        if not appropriate:
            coverage[goal.value] = 1.0
            continue
        in_programs: set[int] = set()
        for program in programs:
            for ex in _iter_program_exercises(program):
                in_programs.add(ex.id)
        coverage[goal.value] = len(appropriate & in_programs) / len(appropriate)
    return coverage


_TOP_K_IOU = 10


def _canonical_profile(goal: HealthGoalFitness, equipment: list[str]) -> FitnessProfileRequest:
    """Profil "full kit / pas de limitation" pour mesurer la couverture catalogue par goal."""
    return FitnessProfileRequest(
        health_goal_fitness=goal,
        experience_level=ExperienceLevel.intermediate,
        equipment=equipment,
        limitations=[],
        preferences=SessionPreferences(),
    )


def _appropriate_by_goal(catalog: list[Exercise]) -> dict[HealthGoalFitness, set[int]]:
    """Pour chaque goal, ids des exercices avec score rule-based > 0.5 sur profil canonique."""
    vocab = derive_vocab(catalog)
    equipment = list(vocab.equipment)
    out: dict[HealthGoalFitness, set[int]] = {}
    for goal in HealthGoalFitness:
        profile = _canonical_profile(goal, equipment)
        out[goal] = {
            ex.id for ex in catalog if score_rule_based(ex, profile, history=[]) > 0.5
        }
    return out


def _top_k_ids(scores_by_id: dict[int, float], k: int) -> list[int]:
    return [
        ex_id for ex_id, _ in sorted(scores_by_id.items(), key=lambda kv: kv[1], reverse=True)[:k]
    ]


def _exercise_ids_in_program(program: WorkoutProgram) -> set[int]:
    return {ex.id for ex in _iter_program_exercises(program)}


def _evaluate_classifier(
    csv_path: Path, model_path: Path
) -> tuple[float, dict[str, int]]:
    """Recharge CSV + model et reproduit le split 60/20/20 pour calculer F1 + CM sur le test set."""
    df = pd.read_csv(csv_path)
    feature_columns = [c for c in df.columns if c not in ("label", "exercise_id")]
    X = df[feature_columns].to_numpy()
    y = df["label"].to_numpy()
    _, _, X_test, _, _, y_test = split_60_20_20(X, y, random_state=42)
    bundle = joblib.load(model_path)
    y_pred = bundle["model"].predict(X_test)
    return f1_classifier(y_test, y_pred, threshold=0.5)


def _generate_program(profile: FitnessProfileRequest, catalog: list[Exercise], history: list):
    return recommend_premium(profile, history=history, catalog=catalog)


def _ml_iou_matrix(
    profiles: list[FitnessProfileRequest],
    catalog: list[Exercise],
) -> tuple[float, list[list[float]]]:
    """IoU rule vs ML par profil + matrice NxN (IoU rule(i) vs ml(j))."""
    rule_tops: list[list[int]] = []
    ml_tops: list[list[int]] = []
    for profile in profiles:
        rule_scores = {ex.id: score_rule_based(ex, profile, []) for ex in catalog}
        ml_scores = {ex.id: scoring_ml.score_exercise(ex, profile) for ex in catalog}
        rule_tops.append(_top_k_ids(rule_scores, _TOP_K_IOU))
        ml_tops.append(_top_k_ids(ml_scores, _TOP_K_IOU))
    per_profile = [iou_top_k(r, m, _TOP_K_IOU) for r, m in zip(rule_tops, ml_tops)]
    mean_iou = sum(per_profile) / len(per_profile) if per_profile else 0.0
    matrix = [[iou_top_k(r, m, _TOP_K_IOU) for m in ml_tops] for r in rule_tops]
    return mean_iou, matrix


def _diversity_mean(
    profiles: list[FitnessProfileRequest],
    catalog: list[Exercise],
) -> float:
    """Jaccard moyen entre 2 programmes consecutifs du meme user (premier puis avec history)."""
    from app.services.scoring_rule_based import Recommendation

    indices: list[float] = []
    now = pd.Timestamp.now("UTC").to_pydatetime()
    for profile in profiles:
        first = _generate_program(profile, catalog, history=[])
        first_ids = _exercise_ids_in_program(first)
        history = [
            Recommendation(exercise_id=ex_id, feedback_score=None, created_at=now)
            for ex_id in first_ids
        ]
        second = _generate_program(profile, catalog, history=history)
        indices.append(jaccard_similarity(first_ids, _exercise_ids_in_program(second)))
    return sum(indices) / len(indices) if indices else 0.0


def _latency_run(
    profiles: list[FitnessProfileRequest], catalog: list[Exercise]
) -> tuple[list[float], list[WorkoutProgram]]:
    """Mesure la latence de `recommend_premium` une fois par profil et collecte les programmes."""
    durations_ms: list[float] = []
    programs: list[WorkoutProgram] = []
    for profile in profiles:
        t0 = time.perf_counter()
        program = _generate_program(profile, catalog, history=[])
        durations_ms.append((time.perf_counter() - t0) * 1000)
        programs.append(program)
    return durations_ms, programs


_HITL_METHODOLOGY = (
    "Tirage aleatoire de 20 programmes parmi ceux generes (metrics.json -> "
    "champ `programs`). Chaque programme est note 1-5 sur la coherence "
    "(adequation goal/level/equipement, progression, varietes muscles travailles) "
    "par 2 evaluateurs independants. Score retenu = moyenne des 2."
)


def run_evaluation(
    catalog: list[Exercise],
    n_profiles: int,
    output_dir: Path,
    seed: int = 42,
) -> EvaluationReport:
    """Pipeline complet RF-14 : entraine un modele, evalue 7 metriques, ecrit livrables."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = output_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="eval_metrics_") as raw_workdir:
        workdir = Path(raw_workdir)
        csv_path = workdir / "scoring_dataset.csv"
        model_path = workdir / "scoring_model.pkl"
        training_report_path = workdir / "training_report.json"

        df = build_dataset(catalog, n_profiles=n_profiles, seed=seed)
        write_dataset(df, csv_path)
        train_and_persist(csv_path, model_path, training_report_path)

        f1, cm = _evaluate_classifier(csv_path, model_path)

        previous_model_path = scoring_ml.MODEL_PATH
        scoring_ml.MODEL_PATH = model_path
        scoring_ml.reset_model()
        try:
            vocab = derive_vocab(catalog)
            profiles = generate_profiles(n_profiles=n_profiles, vocab=vocab, seed=seed)

            durations_ms, programs = _latency_run(profiles, catalog)
            p50_ms, p95_ms = latency_percentiles(durations_ms)

            violation_rate = constraint_violation_rate(
                list(zip(programs, profiles))
            )

            appropriate = _appropriate_by_goal(catalog)
            programs_by_goal: dict[HealthGoalFitness, list[WorkoutProgram]] = {
                goal: [] for goal in HealthGoalFitness
            }
            for profile, program in zip(profiles, programs):
                programs_by_goal[profile.health_goal_fitness].append(program)
            coverage = goal_coverage(programs_by_goal, appropriate)

            diversity = _diversity_mean(profiles, catalog)
            iou_mean, iou_matrix = _ml_iou_matrix(profiles, catalog)
        finally:
            scoring_ml.MODEL_PATH = previous_model_path
            scoring_ml.reset_model()

    report = EvaluationReport(
        classifier_f1=f1,
        confusion_matrix=cm,
        constraint_violation_rate=violation_rate,
        goal_coverage=coverage,
        diversity_jaccard=diversity,
        iou_rule_vs_ml=iou_mean,
        latency_p50_ms=p50_ms,
        latency_p95_ms=p95_ms,
        n_programs=len(programs),
        seed=seed,
        catalog_size=len(catalog),
        hitl_methodology=_HITL_METHODOLOGY,
    )

    plot_confusion_matrix(cm, metrics_dir / "confusion_matrix.png")
    plot_latency_boxplot(durations_ms, metrics_dir / "latency_boxplot.png")
    plot_iou_heatmap(
        iou_matrix,
        [f"p{i}" for i in range(len(iou_matrix))],
        metrics_dir / "iou_heatmap.png",
    )

    (output_dir / "metrics.json").write_text(json.dumps(render_metrics_json(report), indent=2))
    (output_dir / "metrics.md").write_text(render_metrics_markdown(report))
    return report
