import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.db.mongo import close_mongo
from app.routers.fitness_profile import router as fitness_profile_router
from app.routers.health import router as health_router
from app.routers.program_history import router as program_history_router
from app.routers.programs import router as programs_router
from app.routers.recommendations import limiter
from app.routers.recommendations import router as recommendations_router

logger = logging.getLogger(__name__)

# CORS : origines front autorisees (dev local + container front).
# Liste configurable via CORS_ALLOW_ORIGINS (separe par virgules).
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if o.strip()
]


def _cors_headers_for(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin", "")
    if origin in _cors_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


def _rate_limit_handler_with_cors(request: Request, exc: RateLimitExceeded) -> Response:
    """Wrapper du handler slowapi qui ajoute les headers CORS sur la 429.

    CORSMiddleware n'enveloppe pas les reponses emises par les exception handlers ;
    sans ce wrapper, le navigateur affiche "CORS Failed" sur un 429 et masque
    la vraie cause au front.
    """
    response = _rate_limit_exceeded_handler(request, exc)
    response.headers.update(_cors_headers_for(request))
    return response


async def _http_exception_handler_with_cors(
    request: Request, exc: StarletteHTTPException
) -> Response:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_cors_headers_for(request),
    )


async def _unhandled_exception_handler_with_cors(
    request: Request, exc: Exception
) -> Response:
    """Handler global qui ajoute les headers CORS aux 500 non captures.

    Sans ca, une exception levee dans un endpoint (ex. UndefinedColumn SQL)
    remonte a Starlette qui renvoie une 500 sans CORS, et le front voit un
    erreur CORS au lieu de la vraie cause metier.
    """
    logger.exception("Unhandled exception during %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_cors_headers_for(request),
    )

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
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler_with_cors)
app.add_exception_handler(StarletteHTTPException, _http_exception_handler_with_cors)
app.add_exception_handler(Exception, _unhandled_exception_handler_with_cors)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(fitness_profile_router, prefix=API_V1_PREFIX)
app.include_router(recommendations_router, prefix=API_V1_PREFIX)
app.include_router(programs_router, prefix=API_V1_PREFIX)
app.include_router(program_history_router, prefix=API_V1_PREFIX)
