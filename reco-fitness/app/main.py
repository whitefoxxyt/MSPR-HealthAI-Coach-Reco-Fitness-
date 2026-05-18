from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.mongo import close_mongo

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_mongo()


app = FastAPI(
    title="Reco-Fitness API",
    description="Service de recommandations fitness et nutrition base sur l'IA.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Router health enregistre sans prefixe
from app.routers.health import router as health_router  # noqa: E402
app.include_router(health_router)

# Routers metier sous /api/v1
from app.routers.fitness_profile import router as fitness_profile_router  # noqa: E402
app.include_router(fitness_profile_router, prefix=API_V1_PREFIX)
