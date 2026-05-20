from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.db.mongo import close_mongo
from app.routers.fitness_profile import router as fitness_profile_router
from app.routers.health import router as health_router
from app.routers.programs import router as programs_router
from app.routers.recommendations import limiter
from app.routers.recommendations import router as recommendations_router

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_mongo()


app = FastAPI(
    title="Reco-Fitness API",
    description="Service de recommandations fitness et nutrition base sur l'IA.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(health_router)
app.include_router(fitness_profile_router, prefix=API_V1_PREFIX)
app.include_router(recommendations_router, prefix=API_V1_PREFIX)
app.include_router(programs_router, prefix=API_V1_PREFIX)
