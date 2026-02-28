from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.core.logging import logger

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        db_status = "unhealthy"

    return {
        "status": "ok",
        "database": db_status,
    }