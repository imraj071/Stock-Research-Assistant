import os
from app.core.config import settings as _settings

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = _settings.langchain_api_key
os.environ["LANGCHAIN_PROJECT"] = _settings.langchain_project

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.ingestion import router as ingestion_router
from app.api.v1.routes.agent import router as agent_router
from app.api.v1.routes.auth import router as auth_router
from app.services.scheduler import create_scheduler, register_jobs


limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("application_starting", env=settings.app_env)
    logger.info(
        "langsmith_configured",
        project=settings.langchain_project,
        tracing=settings.langchain_tracing_v2,
    )

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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(ingestion_router, prefix="/api/v1/ingest", tags=["ingestion"])
app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])