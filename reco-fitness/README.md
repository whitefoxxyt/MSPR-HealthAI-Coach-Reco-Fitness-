# Reco-Fitness (dossier code)

Repere developpeur pour travailler dans ce sous-dossier. Le [README racine](../README.md) reste la reference pour l'integration et le demarrage de la stack complete. Voir aussi [ARCHITECTURE.md](ARCHITECTURE.md) pour la vision et [CLAUDE.md](CLAUDE.md) pour les conventions IA.

## Demarrage rapide en local

```bash
cp .env.example .env
pip install -r requirements-dev.txt

# Containers Mongo + Postgres + API
docker compose up --build

# Swagger UI
open http://localhost:8002/docs

# Healthcheck
curl http://localhost:8002/health
```

## Tests

```bash
# Unit + integration (Docker requis pour les integration)
pytest

# Unit seuls (sans Docker)
pytest tests/unit tests/test_health.py

# Slow (perf, e2e), deselectes par defaut en CI
pytest -m slow

# Rapport de couverture HTML
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

Cible CI : > 80 % de couverture globale.

## Lint

```bash
ruff check app/ tests/
ruff check --fix app/ tests/
```

## Entrainer le modele de scoring (ML)

```bash
# 1. Generer le dataset synthetique depuis le catalogue PostgreSQL
python scripts/generate_training_data.py --n-profiles 25 --seed 42

# 2. Entrainer le RandomForestRegressor et exporter modele + rapport metrics
python scripts/train_scoring_model.py
```

Artefacts produits :
- `app/data/scoring_model.pkl` : bundle `{model, vocab, feature_columns}` charge par `app/services/scoring_ml.py`.
- `data/training/training_report.json` : metriques validation (MSE, R2) et test (precision, rappel, F1 avec seuil `score > 0.5`).

Cible PRD : F1 > 0.7 sur le jeu de test. Hyperparametres : `n_estimators=200, max_depth=15, random_state=42`, split 60/20/20.

## Evaluer le moteur (RF-14)

```bash
# Catalogue PostgreSQL (par defaut)
python scripts/eval_metrics.py

# Catalogue synthetique offline (utile sans BDD)
python scripts/eval_metrics.py --synthetic 70 --n-profiles 120 --seed 42 --out docs
```

Le dernier `docs/metrics.{json,md}` commit a ete genere avec la deuxieme commande (catalogue synthetique reproductible offline).

Sortie sous `docs/` :
- `docs/metrics.json` : valeurs brutes versionnables (livrable jury).
- `docs/metrics.md` : rendu Markdown (sections classifier, contraintes, couverture, diversite, IoU, latence, HITL).
- `docs/metrics/confusion_matrix.png`, `latency_boxplot.png`, `iou_heatmap.png`.

Le script entraine un RandomForest ephemere a chaque run (`tempfile.TemporaryDirectory`, aucun artefact intermediaire commit). Commande unique, totalement reproductible via le `--seed`.

7 metriques calculees (cf PRD livrable IV) :

| # | Metrique | Cible |
|---|----------|-------|
| 1 | F1 ML classifier (`score > 0.5`) | > 0.8 |
| 2 | Taux de violation des contraintes dures | 0 % |
| 3 | Couverture des objectifs (4 health goals) | > 80 % chacun |
| 4 | Diversite Jaccard (2 programmes consecutifs) | < 0.5 |
| 5 | IoU rule-based vs ML (top-10) | 0.6 - 0.8 |
| 6 | Latence p50 / p95 sur `recommend_premium` | < 200 / < 500 ms |
| 7 | HITL coherence 1-5 (saisi manuellement) | > 3.8/5 |

## Structure du projet

```
reco-fitness/
|-- app/
|   |-- main.py             # Instance FastAPI, OpenAPI metadata
|   |-- config.py           # Variables d'environnement (Pydantic Settings)
|   |-- dependencies.py     # Injection JWT + Mongo
|   |-- openapi_responses.py # Reponses HTTP communes (401, 404, 429, 503)
|   |-- routers/            # 5 routers : health, fitness_profile, recommendations, programs, program_history
|   |-- services/           # Logique metier (scoring, entitlements, biometric, orchestrateur...)
|   |-- schemas/            # DTO Pydantic v2
|   |-- models/             # ORM SQLAlchemy (catalogue PG)
|   |-- db/                 # Connexions Mongo et PG, init_mongo
|   `-- data/               # Poids de scoring + modele ML pickle
|-- tests/
|   |-- conftest.py         # Fixtures partagees (containers, JWT, mock_auth)
|   |-- test_health.py
|   |-- unit/               # Tests rapides sans dependances externes
|   |-- integration/        # Tests avec containers Docker ephemeres
|   `-- slow/               # Tests perf, e2e (exclus de la CI standard)
|-- scripts/                # generate_training_data, train_scoring_model, eval_metrics
|-- docs/                   # metrics.{json,md} + PNG d'evaluation
|-- ARCHITECTURE.md
|-- CLAUDE.md
|-- requirements.txt
|-- requirements-dev.txt
|-- Dockerfile
`-- docker-compose.yml
```
