from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.ingestion import router as ingestion_router
from app.services.scheduler import create_scheduler, register_jobs

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("application_starting", env=settings.app_env)

    scheduler = create_scheduler()
    register_jobs(scheduler)
    scheduler.start()
    logger.info("scheduler_started")

    yield

    scheduler.shutdown()
    logger.info("scheduler_stopped")
    logger.info("application_shutting_down")


app = FastAPI(
    title="Stock Research Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(ingestion_router, prefix="/api/v1/ingest", tags=["ingestion"])