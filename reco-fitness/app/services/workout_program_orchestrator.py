"""
Orchestrateur de programmes d'entrainement (RF-10).

Compose le scoring (rule-based seul ou fusionne avec ML) selon le tier de l'utilisateur
et structure la liste d'exercices selectionnes en semaines / seances / exercices.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Literal

from app.schemas.fitness_profile import FitnessProfileRequest, HealthGoalFitness
from app.services.biometric_reader import Biometric
from app.services.exercise_catalog import Exercise
from app.services.scoring_ml import score_exercise as score_ml
from app.services.scoring_rule_based import NO_EQUIPMENT_NEEDED, Recommendation
from app.services.scoring_rule_based import score_exercise as score_rule_based

ScoringStrategy = Literal["rule_based", "hybrid_rank_fusion"]


@dataclass
class WorkoutProgram:
    """Programme d'entrainement structure : semaines -> seances -> exercices."""

    weeks: list[list[list[Exercise]]]
    duration_weeks: int
    scoring_strategy: ScoringStrategy


# Mapping goal -> (sessions_per_week, exercises_per_session, premium_duration_weeks)
# Free force toujours duration_weeks=2 (cf PRD Q4). sessions et exercices ne
# servent que de repli : les preferences du profil (sessions_per_week,
# duration_min_per_session) priment quand elles sont presentes.
_GOAL_SHAPE: dict[str, tuple[int, int, int]] = {
    "fat_loss": (4, 8, 4),
    "muscle_strength": (4, 6, 6),
    "endurance": (5, 6, 6),
    "general_health": (3, 6, 4),
}
# ~12 min par exercice (echauffement, series, repos), bornes de securite.
_MIN_EXERCISES_PER_SESSION = 3
_MAX_EXERCISES_PER_SESSION = 8
_MAX_SESSIONS_PER_WEEK = 7


def _apply_preferences(
    profile: FitnessProfileRequest,
    sessions_per_week: int,
    exercises_per_session: int,
) -> tuple[int, int]:
    """Le programme doit refleter ce que le profil affiche : seances/semaine
    et duree de seance choisies par l'utilisateur, bornees."""
    prefs = getattr(profile, "preferences", None)
    if prefs is None:
        return sessions_per_week, exercises_per_session
    if prefs.sessions_per_week:
        sessions_per_week = max(1, min(_MAX_SESSIONS_PER_WEEK, prefs.sessions_per_week))
    if prefs.duration_min_per_session:
        exercises_per_session = max(
            _MIN_EXERCISES_PER_SESSION,
            min(
                _MAX_EXERCISES_PER_SESSION,
                int(prefs.duration_min_per_session / 12 + 0.5),
            ),
        )
    return sessions_per_week, exercises_per_session
_FREE_DURATION_WEEKS = 2
_TOP_N_CANDIDATES = 20
# Poids de fusion : rule-based et ML pesent autant. Si besoin de tuning, deporter en data/.
_RANK_FUSION_WEIGHTS = {"rule_based": 0.5, "ml": 0.5}


def _shape_for(goal: HealthGoalFitness) -> tuple[int, int, int]:
    return _GOAL_SHAPE[goal.value]


class EmptyCatalogError(ValueError):
    """Aucun exercice ne passe les filtres durs (limitations / equipement)."""


def _shuffled(items: list[Exercise], rng: random.Random | None) -> list[Exercise]:
    """
    Copie melangee de la liste : le tri stable qui suit conserve l'ordre des
    scores mais randomise les ex aequo. Sans cela, les nombreux exercices a
    score identique sortent toujours dans l'ordre de la table PG et chaque
    regeneration produit un programme strictement identique.
    """
    copy = list(items)
    (rng or random.Random()).shuffle(copy)
    return copy


def _primary_group(exercise: Exercise) -> str:
    if exercise.body_parts:
        return exercise.body_parts[0]
    if exercise.target_muscles:
        return exercise.target_muscles[0]
    return "autre"


def _interleave_by_group(ranked: list[Exercise]) -> list[Exercise]:
    """
    Alterne les groupes corporels (round-robin) en preservant l'ordre de score
    interne a chaque groupe : evite les seances mono-muscle quand le haut du
    classement est domine par un seul groupe.
    """
    buckets: dict[str, deque[Exercise]] = {}
    order: list[str] = []
    for ex in ranked:
        key = _primary_group(ex)
        if key not in buckets:
            buckets[key] = deque()
            order.append(key)
        buckets[key].append(ex)
    result: list[Exercise] = []
    while len(result) < len(ranked):
        for key in order:
            if buckets[key]:
                result.append(buckets[key].popleft())
    return result


def _structure_program(
    ranked: list[Exercise],
    duration_weeks: int,
    sessions_per_week: int,
    exercises_per_session: int,
    strategy: ScoringStrategy,
) -> WorkoutProgram:
    """Decoupe la liste d'exercices ranges en semaines de seances, en cyclant si necessaire."""
    if not ranked:
        raise EmptyCatalogError(
            "Aucun exercice eligible apres filtrage : limitations ou equipement trop restrictifs."
        )
    ranked = _interleave_by_group(ranked)
    needed_per_week = sessions_per_week * exercises_per_session
    weeks: list[list[list[Exercise]]] = []
    for w in range(duration_weeks):
        week_sessions: list[list[Exercise]] = []
        for s in range(sessions_per_week):
            session: list[Exercise] = []
            for e in range(exercises_per_session):
                # On cycle sur la liste rangee pour combler le programme meme quand
                # le catalogue filtre est plus petit que weeks * sessions * exercises.
                idx = (w * needed_per_week + s * exercises_per_session + e) % len(ranked)
                session.append(ranked[idx])
            week_sessions.append(session)
        weeks.append(week_sessions)
    return WorkoutProgram(
        weeks=weeks,
        duration_weeks=duration_weeks,
        scoring_strategy=strategy,
    )


# Le profil exprime les limitations en articulations (vocabulaire du front),
# le catalogue en muscles cibles ExerciseDB : sans ce mapping, une limitation
# "knee" ne filtrait strictement rien.
_LIMITATION_MUSCLES: dict[str, list[str]] = {
    "knee": ["quads", "hamstrings", "calves", "abductors", "adductors", "glutes"],
    "back": ["spine", "upper back", "lats", "traps", "levator scapulae"],
    "shoulder": ["delts", "serratus anterior"],
    "wrist": ["forearms"],
    "ankle": ["calves"],
    "hip": ["glutes", "abductors", "adductors", "hamstrings"],
}

# Le catalogue ExerciseDB distingue "band" et "resistance band" : posseder
# l'un donne acces aux exercices de l'autre.
_EQUIPMENT_SYNONYMS: dict[str, list[str]] = {
    "band": ["resistance band"],
    "resistance band": ["band"],
}


def _expand_limitations(limitations: list[str]) -> list[str]:
    expanded = list(limitations)
    for lim in limitations:
        expanded.extend(_LIMITATION_MUSCLES.get(lim, []))
    return sorted(set(expanded))


def _expand_equipment(equipment: list[str]) -> list[str]:
    expanded = list(equipment)
    for item in equipment:
        expanded.extend(_EQUIPMENT_SYNONYMS.get(item, []))
    return sorted(set(expanded))


def prepare_profile(profile: FitnessProfileRequest) -> FitnessProfileRequest:
    """Profil normalise pour le scoring : limitations en muscles, synonymes d'equipement."""
    return profile.model_copy(
        update={
            "limitations": _expand_limitations(profile.limitations),
            "equipment": _expand_equipment(profile.equipment),
        }
    )


def passes_hard_filters(exercise: Exercise, profile: FitnessProfileRequest) -> bool:
    """Ecarte un exercice qui touche une limitation ou requiert un equipement absent."""
    limitations = set(profile.limitations)
    if limitations & set(exercise.target_muscles):
        return False
    if exercise.category and exercise.category in limitations:
        return False
    required = [e for e in exercise.equipment if e not in NO_EQUIPMENT_NEEDED]
    owned = set(profile.equipment)
    if required and not all(item in owned for item in required):
        return False
    return True


def _rank_fusion(
    rule_based_ranking: list[Exercise],
    ml_ranking: list[Exercise],
) -> list[Exercise]:
    """
    Fusionne 2 Top-N par moyenne ponderee des rangs.
    Un exercice absent d'une liste herite du rang max+1 de cette liste.
    Retourne les exercices ordonnes par rang fusionne croissant.
    """
    missing_rb = len(rule_based_ranking)
    missing_ml = len(ml_ranking)
    rb_rank = {ex.id: i for i, ex in enumerate(rule_based_ranking)}
    ml_rank = {ex.id: i for i, ex in enumerate(ml_ranking)}

    seen: dict[int, Exercise] = {}
    for ex in rule_based_ranking + ml_ranking:
        seen.setdefault(ex.id, ex)

    def fused_rank(ex: Exercise) -> float:
        r1 = rb_rank.get(ex.id, missing_rb)
        r2 = ml_rank.get(ex.id, missing_ml)
        return _RANK_FUSION_WEIGHTS["rule_based"] * r1 + _RANK_FUSION_WEIGHTS["ml"] * r2

    return sorted(seen.values(), key=fused_rank)


def recommend_free(
    profile: FitnessProfileRequest,
    history: list[Recommendation],
    catalog: list[Exercise],
    rng: random.Random | None = None,
) -> WorkoutProgram:
    """Tier free : scoring rule-based seul, programme de 2 semaines."""
    profile = prepare_profile(profile)
    sessions_per_week, exercises_per_session, _ = _shape_for(profile.health_goal_fitness)
    sessions_per_week, exercises_per_session = _apply_preferences(
        profile, sessions_per_week, exercises_per_session
    )
    eligible = [ex for ex in catalog if passes_hard_filters(ex, profile)]
    ranked = sorted(
        _shuffled(eligible, rng),
        key=lambda ex: score_rule_based(ex, profile, history),
        reverse=True,
    )
    return _structure_program(
        ranked=ranked,
        duration_weeks=_FREE_DURATION_WEEKS,
        sessions_per_week=sessions_per_week,
        exercises_per_session=exercises_per_session,
        strategy="rule_based",
    )


def _hybrid_ranked(
    profile: FitnessProfileRequest,
    history: list[Recommendation],
    catalog: list[Exercise],
    rng: random.Random | None = None,
) -> list[Exercise]:
    """Top-N rule-based ∪ Top-N ML, fusionnes par rang (filtre dur applique en amont)."""
    profile = prepare_profile(profile)
    eligible = _shuffled(
        [ex for ex in catalog if passes_hard_filters(ex, profile)], rng
    )
    top_rule_based = sorted(
        eligible,
        key=lambda ex: score_rule_based(ex, profile, history),
        reverse=True,
    )[:_TOP_N_CANDIDATES]
    top_ml = sorted(
        eligible,
        key=lambda ex: score_ml(ex, profile),
        reverse=True,
    )[:_TOP_N_CANDIDATES]
    return _rank_fusion(top_rule_based, top_ml)


def recommend_premium(
    profile: FitnessProfileRequest,
    history: list[Recommendation],
    catalog: list[Exercise],
    rng: random.Random | None = None,
) -> WorkoutProgram:
    """
    Tier premium : fusion Top-N rule-based + ML, duree pleine selon goal,
    feedback adaptive actif (history utilisee dans novelty_and_feedback_score).
    """
    sessions_per_week, exercises_per_session, duration_weeks = _shape_for(
        profile.health_goal_fitness
    )
    sessions_per_week, exercises_per_session = _apply_preferences(
        profile, sessions_per_week, exercises_per_session
    )
    return _structure_program(
        ranked=_hybrid_ranked(profile, history, catalog, rng),
        duration_weeks=duration_weeks,
        sessions_per_week=sessions_per_week,
        exercises_per_session=exercises_per_session,
        strategy="hybrid_rank_fusion",
    )


# Seuil d'attenuation : FC moyenne elevee = signal de fatigue/surentrainement.
# RF-11 acceptance criteria : avg_heart_rate_bpm > 80 -> -1 seance/semaine.
_AVG_HR_HIGH_BPM = 80
_MIN_SESSIONS_PER_WEEK = 1


def _sessions_adjustment(biometrics: Biometric | None) -> int:
    """Retourne le delta a appliquer au nb de seances/semaine selon les biometriques."""
    if biometrics is None or biometrics.avg_heart_rate_bpm is None:
        return 0
    if biometrics.avg_heart_rate_bpm > _AVG_HR_HIGH_BPM:
        return -1
    return 0


def recommend_premium_plus(
    profile: FitnessProfileRequest,
    history: list[Recommendation],
    catalog: list[Exercise],
    biometrics: Biometric | None,
    rng: random.Random | None = None,
) -> WorkoutProgram:
    """
    Tier premium_plus : meme moteur que premium, enrichi d'un ajustement de la
    charge a partir des biometriques recentes. Quand biometrics=None ou que la
    FC moyenne n'est pas elevee, comportement equivalent a premium.
    """
    base_sessions, exercises_per_session, duration_weeks = _shape_for(
        profile.health_goal_fitness
    )
    base_sessions, exercises_per_session = _apply_preferences(
        profile, base_sessions, exercises_per_session
    )
    sessions_per_week = max(
        _MIN_SESSIONS_PER_WEEK,
        base_sessions + _sessions_adjustment(biometrics),
    )
    return _structure_program(
        ranked=_hybrid_ranked(profile, history, catalog, rng),
        duration_weeks=duration_weeks,
        sessions_per_week=sessions_per_week,
        exercises_per_session=exercises_per_session,
        strategy="hybrid_rank_fusion",
    )
