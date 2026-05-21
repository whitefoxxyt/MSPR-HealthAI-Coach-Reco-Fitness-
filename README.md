# MSPR-Reco-Fitness

Microservice de **recommandations fitness** de la plateforme HealthAI Coach (MSPR2).

Reference fonctionnelle : [PRD #13](https://github.com/whitefoxxyt/MSPR-HealthAI-Coach-Reco-Fitness-/issues/13). Plan technique : tickets RF-1 a RF-16.

Le service expose une API REST qui genere des programmes d'entrainement
personnalises en combinant un scoring rule-based explicable et un modele
d'apprentissage RandomForest. La personnalisation est graduelle selon le tier
d'abonnement de l'utilisateur (`free`, `premium`, `premium_plus`), determine
par appel a MSPR-AUTH.

Vision et decisions d'architecture : [ARCHITECTURE.md](reco-fitness/ARCHITECTURE.md).
Conventions pour Claude Code : [CLAUDE.md](reco-fitness/CLAUDE.md).

---

## Stack technique

| Composant | Role |
|-----------|------|
| **FastAPI** + uvicorn | API REST asynchrone, generation OpenAPI |
| **scikit-learn** (RandomForestRegressor) | Modele de scoring entraine sur dataset synthetique |
| **MongoDB** (motor) | Profils utilisateurs, programmes generes, historique de feedback |
| **PostgreSQL** (SQLAlchemy, read-only) | Catalogue des exercices (table `exercises` de MSPR-DB) |
| **MSPR-AUTH** (httpx + cache TTL 60s) | Validation JWT et lecture des entitlements (tier d'abonnement) |
| **SlowAPI** | Rate limiting par utilisateur sur `POST /recommendations` |

Python 3.12, Pydantic v2.

---

## Demarrage local

### Avec la stack complete (recommande)

Le service est integre dans le `docker-compose.yml` racine `/home/arthur/Projects/MSPR/` :

```bash
cd /home/arthur/Projects/MSPR
docker compose up -d --build reco-fitness
```

Cela demarre PostgreSQL (MSPR-DB), MongoDB (MSPR-MongoDB), MSPR-AUTH et le service Reco-Fitness, sur le reseau Docker `mspr_data_network`.

### En standalone

```bash
cd MSPR-Reco-Fitness/reco-fitness
cp .env.example .env  # editer les valeurs si besoin
docker compose up -d --build
```

Ports exposes :

| Service | Port |
|---------|------|
| API Reco-Fitness | 8002 |
| MongoDB (standalone) | 27018 |
| PostgreSQL (standalone) | 5433 |

Documentation interactive : http://localhost:8002/docs (Swagger UI) ou http://localhost:8002/redoc.

### Variables d'environnement

Voir [`reco-fitness/.env.example`](reco-fitness/.env.example) pour la liste complete.

| Variable | Defaut | Role |
|----------|--------|------|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | localhost:5432 | PostgreSQL (catalogue exercises) |
| `MONGO_URI`, `MONGO_DATABASE` | mongodb://localhost:27017 / reco_fitness | MongoDB |
| `BETTER_AUTH_SECRET` | changeme | Secret partage MSPR-AUTH (HS256 JWT) |
| `AUTH_API_URL` | http://localhost:8001 | URL du service MSPR-AUTH |

---

## Endpoints

Tous les endpoints `/api/v1` requierent un header `Authorization: Bearer <jwt>` emis par MSPR-AUTH.

| Methode | Chemin | Tag | Description |
|---------|--------|-----|-------------|
| GET | `/health` | Sante | Liveness/readiness (PostgreSQL, MongoDB, MSPR-AUTH) |
| GET | `/api/v1/fitness-profile/me` | Profil | Lecture du profil fitness de l'utilisateur |
| PUT | `/api/v1/fitness-profile/me` | Profil | Creation ou mise a jour du profil (upsert) |
| POST | `/api/v1/recommendations` | Recommandations | Generation d'un programme personnalise (rate-limite 10/h, 3/min) |
| PUT | `/api/v1/programs/{program_id}/feedback` | Feedback | Enregistrement d'un feedback utilisateur (idempotent) |
| GET | `/api/v1/programs/me` | Historique | Liste paginee des programmes generes |
| GET | `/api/v1/feedback/me` | Historique | Liste paginee des feedbacks envoyes |

Codes d'erreur HTTP documentes : 401 (JWT manquant ou invalide), 403 (acces a une ressource d'un autre utilisateur), 404 (ressource introuvable), 409 (filtres trop restrictifs sur le catalogue), 422 (corps de requete invalide), 429 (quota depasse), 503 (dependance externe injoignable). Voir le schema OpenAPI pour le detail.

---

## Tests

```bash
cd reco-fitness

# Installation des dependances dev
pip install -r requirements-dev.txt

# Suite complete (unit + integration via testcontainers)
pytest

# Unit uniquement (rapide, sans Docker)
pytest tests/unit tests/test_health.py

# Slow tests (perf, e2e eval), deselectes par defaut en CI
pytest -m slow
```

Couverture : `htmlcov/index.html` apres `pytest`. Cible globale > 80 %.

---

## Metriques d'evaluation du moteur

Le script `scripts/eval_metrics.py` produit un rapport reproductible des 7 metriques du PRD (RF-14) :

```bash
cd reco-fitness
python scripts/eval_metrics.py
```

Sorties dans `docs/` : `metrics.json` (valeurs brutes versionnables), `metrics.md` (livrable jury), 3 PNG (matrice de confusion, latence, IoU).

Resume des resultats actuels : [`reco-fitness/docs/metrics.md`](reco-fitness/docs/metrics.md).

---

## Re-entrainement du modele ML

Le modele de scoring (`reco-fitness/app/data/scoring_model.pkl`) est entraine sur un dataset synthetique de 5000+ paires `(exercice, profil)` etiquetees par le scoring rule-based qui sert d'oracle. Procedure documentee dans le ticket RF-15.

```bash
cd reco-fitness

# 1. Regenerer le dataset depuis le catalogue PostgreSQL
python scripts/generate_training_data.py --n-profiles 25 --seed 42

# 2. Entrainer un nouveau modele + rapport metrics
python scripts/train_scoring_model.py
```

Le dossier `data/training/` est gitignore : le dataset est regenerable a tout moment.

Hyperparametres : `RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42)`, split 60/20/20. Cible PRD : F1 > 0.7 sur le jeu de test (`score > 0.5`).

---

## Limitations connues

- **Fallback degrade tier free** : si MSPR-AUTH est injoignable (timeout 3s), le service repond systematiquement comme si l'utilisateur etait free. Aucune erreur exposee au client. Choix delibere pour la disponibilite.
- **Catalogue PostgreSQL** : mis en cache 1h en memoire. Une mise a jour du catalogue ne sera prise en compte qu'au prochain TTL ou au redemarrage du service.
- **Rate limiting in-memory** : SlowAPI utilise un compteur en memoire process-local. En multi-instance, les quotas ne sont pas partages entre processus. Acceptable pour le scope MSPR2, a remplacer par Redis pour la prod.
- **Decode JWT local** : la cle `BETTER_AUTH_SECRET` est partagee avec MSPR-AUTH. Pas de validation de revocation : un JWT vole reste valide jusqu'a expiration.
- **Cycle de rappel des exercices** : quand le catalogue filtre est plus petit que `weeks x sessions x exercises`, l'orchestrateur cycle sur la liste rangee pour combler le programme. Pas de garantie de diversite hebdomadaire dans ce cas degrade.
- **Endpoint admin entitlements** : le passage d'un utilisateur en tier `premium` ou `premium_plus` est cote MSPR-AUTH. Pas d'endpoint admin cote Reco-Fitness.
