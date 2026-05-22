"""End-to-end : `run_evaluation` produit JSON + MD + 3 PNG sur petit catalogue (slow)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services import eval_metrics
from app.services.exercise_catalog import Exercise


def _realistic_catalog(n: int = 24) -> list[Exercise]:
    categories = ["cardio", "strength", "flexibility"]
    difficulties = ["beginner", "intermediate", "advanced"]
    equipments = [["none"], ["dumbbells"], ["barbell", "rack"], ["kettlebell"]]
    muscles = [["chest"], ["quadriceps", "glutes"], ["back"], ["shoulders"], ["abs"]]
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
def test_run_evaluation_produces_all_deliverables(tmp_path: Path):
    catalog = _realistic_catalog(24)
    output_dir = tmp_path / "docs"

    report = eval_metrics.run_evaluation(
        catalog=catalog,
        n_profiles=12,
        output_dir=output_dir,
        seed=42,
    )

    metrics_json = output_dir / "metrics.json"
    metrics_md = output_dir / "metrics.md"
    cm_png = output_dir / "metrics" / "confusion_matrix.png"
    lat_png = output_dir / "metrics" / "latency_boxplot.png"
    iou_png = output_dir / "metrics" / "iou_heatmap.png"

    for path in (metrics_json, metrics_md, cm_png, lat_png, iou_png):
        assert path.exists(), f"Sortie manquante : {path}"
    assert cm_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert lat_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert iou_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    data = json.loads(metrics_json.read_text())
    assert {
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
    } <= set(data.keys())

    md = metrics_md.read_text()
    assert "## Classifier" in md
    assert "## Latence" in md
    assert "## Evaluation humaine (HITL)" in md

    # Report retourne == JSON ecrit
    assert data["classifier_f1"] == pytest.approx(report.classifier_f1)
    assert data["catalog_size"] == 24
