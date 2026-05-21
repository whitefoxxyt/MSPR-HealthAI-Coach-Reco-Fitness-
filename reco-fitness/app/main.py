from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.db.mongo import close_mongo
from app.routers.fitness_profile import router as fitness_profile_router
from app.routers.health import router as health_router
from app.routers.program_history import router as program_history_router
from app.routers.programs import router as programs_router
from app.routers.recommendations import limiter
from app.routers.recommendations import router as recommendations_router

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_mongo()


APP_DESCRIPTION = """
Microservice de recommandations fitness de la plateforme **HealthAI Coach** (MSPR2).

Genere des programmes d'entrainement personnalises en combinant un scoring
rule-based explicable et un modele d'apprentissage RandomForest, avec une
personnalisation graduelle suivant le tier d'abonnement de l'utilisateur :

- `free` : scoring rule-based seul, programme 2 semaines.
- `premium` : fusion rule-based + ML, duree pleine, feedback adaptive actif.
- `premium_plus` : meme moteur, ajuste a la charge biometrique recente.

Reference fonctionnelle : PRD #13. Plan technique RF-1 a RF-16.
Authentification : JWT Bearer emis par MSPR-AUTH (`Authorization: Bearer ...`).
Routes versionnees `/api/v1/...`. Endpoint `/health` non versionne.
"""

OPENAPI_TAGS = [
    {"name": "Sante", "description": "Sondes de disponibilite (liveness, readiness)."},
    {"name": "Profil", "description": "Profil fitness de l'utilisateur (Mongo)."},
    {
        "name": "Recommandations",
        "description": (
            "Generation de programmes personnalises. Rate-limite 10/heure et 3/minute par user."
        ),
    },
    {
        "name": "Feedback",
        "description": "Retour utilisateur (note, completion, commentaire) sur un programme.",
    },
    {
        "name": "Historique",
        "description": "Lecture paginee des programmes generes et feedbacks envoyes.",
    },
]


app = FastAPI(
    title="Reco-Fitness API",
    description=APP_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(health_router)
app.include_router(fitness_profile_router, prefix=API_V1_PREFIX)
app.include_router(recommendations_router, prefix=API_V1_PREFIX)
app.include_router(programs_router, prefix=API_V1_PREFIX)
app.include_router(program_history_router, prefix=API_V1_PREFIX)
