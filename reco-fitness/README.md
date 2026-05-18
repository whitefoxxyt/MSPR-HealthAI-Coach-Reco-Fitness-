# Reco-Fitness

Microservice FastAPI de recommandations fitness et nutrition base sur l'IA.
Fait partie du projet MSPR HealthAI Coach.

## Demarrage rapide

```bash
# Lancer les services (PostgreSQL + MongoDB + API)
docker network create mspr_data_network
docker compose up --build

# Swagger UI
open http://localhost:8002/docs

# Health check
curl http://localhost:8002/health
```

## Developpement

### Installation

```bash
cd reco-fitness
cp .env.example .env
pip install -r requirements-dev.txt
```

### Lancer les tests

```bash
# Tests unitaires et d'integration rapides (sans Docker requis pour les tests unitaires)
pytest -m "not slow"

# Avec rapport de couverture HTML
pytest -m "not slow" --cov=app --cov-report=html
open htmlcov/index.html

# Tests d'integration uniquement (Docker requis)
pytest -m integration

# Tests slow (appels reseau reels)
pytest -m slow

# Tous les tests
pytest
```

### Couverture cible

La CI echoue si la couverture descend sous **80 %**.

### Lint

```bash
ruff check app/ tests/
ruff check --fix app/ tests/
```

## Structure du projet

```
reco-fitness/
├── app/
│   ├── config.py          # Variables d'environnement (Pydantic Settings)
│   ├── main.py            # Instance FastAPI
│   ├── routers/           # Endpoints HTTP
│   ├── services/          # Logique metier
│   ├── db/                # Connexions BDD
│   └── models/            # Modeles SQLAlchemy
├── tests/
│   ├── conftest.py        # Fixtures partagees (containers, JWT, mock_auth)
│   ├── unit/              # Tests unitaires rapides
│   ├── integration/       # Tests avec containers Docker ephemeres
│   └── slow/              # Tests reseau reels (exclus de la CI standard)
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
└── docker-compose.yml
```

## Variables d'environnement

Voir `.env.example` pour la liste complete des variables.

| Variable | Description | Defaut |
|---|---|---|
| `DB_HOST` | Hote PostgreSQL | `localhost` |
| `DB_PORT` | Port PostgreSQL | `5432` |
| `DB_NAME` | Nom de la base | `reco_fitness` |
| `DB_USER` | Utilisateur PostgreSQL | `postgres` |
| `DB_PASSWORD` | Mot de passe PostgreSQL | `postgres` |
| `MONGO_URI` | URI MongoDB | `mongodb://localhost:27017` |
| `MONGO_DATABASE` | Nom de la base MongoDB | `reco_fitness` |
| `BETTER_AUTH_SECRET` | Secret partage avec MSPR-AUTH | `changeme` |
| `AUTH_API_URL` | URL du service MSPR-AUTH | `http://localhost:8001` |
