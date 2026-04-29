from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers.health import router as health_router
from app.db.mongo import close_mongo


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

# Enregistrement du router health sans prefixe
app.include_router(health_router)

# Routers metier enregistres sous /api/v1
API_V1_PREFIX = "/api/v1"

# Exemple d'inclusion conditionnelle pour les futurs routers :
# from app.routers import recommendations, exercises, nutrition
# app.include_router(recommendations.router, prefix=API_V1_PREFIX)
# app.include_router(exercises.router, prefix=API_V1_PREFIX)
# app.include_router(nutrition.router, prefix=API_V1_PREFIX)
