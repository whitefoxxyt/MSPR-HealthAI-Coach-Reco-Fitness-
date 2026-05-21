# CLAUDE.md, MSPR-Reco-Fitness

Instructions ciblees pour Claude Code sur ce repo. Le [CLAUDE.md racine](../../MSPR/CLAUDE.md) reste la reference globale (architecture des 8 repos, reseau Docker, flux d'auth). Ce fichier complete sans dupliquer.

Lire en complement : [ARCHITECTURE.md](ARCHITECTURE.md) (vision, decisions, modules), [README.md racine](../README.md) (demarrage et endpoints).

---

## Role du service

Microservice FastAPI de recommandations fitness, expose sur le port `8002`. Genere des programmes d'entrainement personnalises a partir d'un profil utilisateur, d'un catalogue d'exercices PostgreSQL (read-only) et d'un modele de scoring hybride (rule-based + RandomForest).

Persistance : MongoDB (profils, programmes generes, historique feedback). Lecture seule PG (catalogue exercices, biometriques Premium+). Auth deleguee a MSPR-AUTH.

---

## Avancement (au 2026-05-21)

| Phase / Ticket | Statut |
|----------------|--------|
| RF-1, init repo + squelette FastAPI | OK |
| RF-2, init MongoDB (repo MSPR-MongoDB) | OK |
| RF-3, healthcheck | OK |
| RF-4, jwt_decoder local | OK |
| RF-5, entitlements_client + cache + degrade | OK |
| RF-6, CRUD fitness profile | OK |
| RF-7, exercise_catalog cache PG | OK |
| RF-8, scoring rule-based + poids par goal | OK |
| RF-9, training_data + scoring_trainer + scoring_ml | OK |
| RF-10, POST /recommendations (orchestrateur free/premium) | OK |
| RF-11, biometric_reader + premium_plus | OK |
| RF-12, PUT feedback idempotent | OK |
| RF-13, GET /programs/me + /feedback/me | OK |
| RF-14, eval_metrics + docs/metrics.{json,md} + PNG | OK |
| RF-15, procedure de re-entrainement | en cours |
| RF-16, doc OpenAPI + README + ARCHITECTURE + CLAUDE | OK (cette issue) |

Tous les tickets bloquant RF-16 sont mergeables ou merges. La couverture globale est > 80 %.

---

## Pieges connus, a verifier avant tout changement

Ces ecarts entre le contrat apparent et la realite du code sont importants. Claude doit les connaitre pour ne pas proposer de fix qui aggraveraient la situation.

### 1. Tags OpenAPI en francais, verrouilles par test

Tags officiels : `Sante`, `Profil`, `Recommandations`, `Feedback`, `Historique`. Le test `tests/unit/test_openapi.py::test_all_endpoints_use_official_tags` casse si tu ajoutes un tag hors liste. Pour un nouveau endpoint, reutilise un tag existant ou modifie d'abord la liste `OFFICIAL_TAGS` du test.

### 2. Le prefixe URL et le tag OpenAPI peuvent diverger

Le router `programs.py` est prefixe `/programs` mais tagge `Feedback` (choix produit, pas un bug). Ne renomme pas l'un sans verifier l'autre.

### 3. `user_id` est une chaine opaque venant du JWT

Le JWT emis par MSPR-AUTH peut contenir un id numerique ou un UUID. Le code suppose une `str` partout (Mongo) et tente `int(user_id)` ponctuellement pour PG (biometric_reader). Ne pas faire de validation Pydantic stricte sur le format.

### 4. Le `user_id` ne doit jamais venir de l'URL ou du body

Tous les endpoints metier ont un pattern `/me` ou `/{program_id}/feedback`. Le `user_id` est toujours extrait du JWT (`current_user.user_id`). Si tu ajoutes un endpoint qui accepte un `user_id` en parametre, c'est un bug de securite.

### 5. Le degrade silencieux vers `tier=free` masque les erreurs MSPR-AUTH

`entitlements_client.get_entitlements` n'expose aucune exception : timeout, 5xx, JSON invalide -> tous retournent `Entitlements(tier="free", ...)`. Avantage : disponibilite. Inconvenient : un bug d'integration MSPR-AUTH est invisible cote client. Pour debug : verifier `AUTH_API_URL` puis les logs du container MSPR-AUTH.

### 6. Cache catalogue PG TTL 1h, process-local

`exercise_catalog.get_all` met en cache 1h. Une migration `MSPR-DB` qui modifie la table `exercises` n'est prise en compte qu'apres redemarrage ou expiration. En multi-instance, chaque process a son cache propre.

### 7. Rate-limit SlowAPI in-memory, process-local

Idem cache : compteurs en RAM, pas partages entre processus. Acceptable au scope MSPR2. Pour la prod, passer a `slowapi[redis]`.

### 8. `RecommendationRequest` est un Pydantic vide

`POST /recommendations` ne lit aucun parametre du body. Tout vient du profil Mongo + du JWT. Si tu ajoutes des parametres, decide explicitement de la priorite (body > profil ou inverse) et documente le choix dans `ARCHITECTURE.md`.

### 9. Le scoring rule-based sert d'oracle au ML

Le dataset d'entrainement est genere par `services/training_data.py` et etiquete par `scoring_rule_based.score_exercise`. Si tu modifies le rule-based, le ML devient invalide jusqu'au prochain re-entrainement (et son F1 chute). Regenerer + retrainer dans le meme commit.

### 10. PUT feedback idempotent sur cle `(user_id, program_id, exercise_id)`

`feedback_service.record_feedback` upsert sur cette cle composee. Plusieurs PUT successifs ne creent pas de doublons. `exercise_id=None` represente un feedback program-level (different d'un feedback granulaire par exercice).

### 11. Mongo `tz_aware=True` requis pour les datetimes

Les services stockent `datetime.now(timezone.utc)`. Tout client Mongo qui relit ces documents doit etre cree avec `tz_aware=True`, sinon Pydantic v2 refuse le `datetime` naive. La fixture `mongo_db` du `conftest.py` le fait deja.

---

## Stack & conventions

- **Python 3.12**, FastAPI 0.111+, SQLAlchemy 2.0 (style `DeclarativeBase`), Pydantic v2, motor 3.4+, scikit-learn 1.5+.
- **Auth** : HS256 JWT local avec `BETTER_AUTH_SECRET` partage. Module `services/jwt_decoder.py`, quasi-conforme a celui d'AI-Nutrition.
- **Endpoints metier** : prefixe `/api/v1/`. Endpoint `/health` non versionne.
- **Pattern `/me`** : tout endpoint utilisateur. Le `user_id` vient du JWT, jamais de l'URL.
- **Reseaux Docker** : `mspr_data_network` (external, cree par le compose racine).
- **Imports** : `from __future__ import annotations` en tete des fichiers Python (sauf `__init__.py`).
- **Reponses HTTP communes** : centralisees dans `app/openapi_responses.py`. Utiliser `auth_responses()` au niveau du `APIRouter`, ajouter `NOT_FOUND`, `RATE_LIMITED` selon besoin.

---

## Commandes courantes

```bash
# Demarrage standalone
docker compose up -d --build

# Avec le reste de la stack (preferable pour tester l'integration)
cd /home/arthur/Projects/MSPR && docker compose up -d --build

# Healthcheck
curl http://localhost:8002/health

# OpenAPI
open http://localhost:8002/docs

# Tests
pytest                                        # tout
pytest tests/unit tests/test_health.py        # rapide, sans Docker
pytest -m slow                                # perf + e2e, deselectes en CI

# Lint
ruff check app/ tests/
ruff check --fix app/ tests/

# Regenerer dataset + reentrainer modele ML
python scripts/generate_training_data.py --n-profiles 25 --seed 42
python scripts/train_scoring_model.py

# Recalculer les metriques d'evaluation pour le jury (reproductible)
python scripts/eval_metrics.py --synthetic 70 --n-profiles 120 --seed 42 --out docs
```

---

## Workflow git

- **Branche par defaut** : `master`. PR systematique par feature ou par ticket RF.
- **Numerotation** : commits referencent les numeros d'issue / PR (`(#N)` ou `(RF-XX)`). Continuer cette convention.
- **Co-author Claude** : interdit. Aucune mention de Claude Code dans les commits, PR ou issues sauf demande explicite d'Arthur.
- **Push** : pas de SSH agent dans cet env, preparer les commandes pour Arthur plutot que tenter `git push`.
- **Commits francais**. Format `type(scope): description`, ex. `feat(reco): biometric_reader (RF-11)`, `fix(reco): ...`, `test(reco): ...`.

---

## Style de redaction

- **Pas de tirets cadratins** (`,` `:` `-` ASCII a la place). S'applique au code, aux commentaires, aux commit messages et a la doc.
- **Commentaires en francais**, courts. Pas de docstring multi-paragraphes.
- **Guillemets doubles** dans le code Python (style FastAPI / transformers).
- **Ne pas reecrire** les textes d'Arthur (commentaires, README, docs) sans raison forte. Prefere supprimer ou pointer le passage problematique.

---

## Avant de modifier le scoring ou l'orchestrateur

Checklist a derouler dans cet ordre :

1. Lire les tests existants : `tests/unit/test_scoring_rule_based.py`, `test_scoring_ml.py`, `test_workout_program_orchestrator.py`.
2. Si tu modifies le rule-based : regenerer le dataset + reentrainer le ML (sinon le F1 chute). Voir commandes ci-dessus.
3. Si tu ajoutes un parametre a `recommend_*` : faire passer la valeur depuis le router `recommendations.py`, sans modifier la signature pour les tiers qui n'en ont pas besoin.
4. Recalculer les metriques (`scripts/eval_metrics.py`) et verifier qu'on reste dans les cibles PRD (F1 > 0.8, latence p95 < 500 ms, violation contraintes 0 %).
5. Mettre a jour `docs/metrics.{json,md}` si les valeurs changent significativement.
