from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from sqlalchemy import select
from app.core.config import settings
from app.core.logging import logger
from app.models.ticker import Ticker
from app.db.session import AsyncSessionLocal
from app.services.ingestion.edgar import ingest_filings_for_ticker
from app.services.ingestion.yfinance_service import ingest_price_data_for_ticker
from app.services.ingestion.news_service import ingest_news_for_ticker
from app.services.rag.embeddings import process_unprocessed_filings

def create_scheduler() -> AsyncIOScheduler:
    jobstores = {
        "default": RedisJobStore(
            host=settings.redis_host,
            port=settings.redis_port,
        )
    }

    executors = {
        "default": AsyncIOExecutor(),
    }

    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 3600,
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
    )

    return scheduler


async def job_ingest_price_data() -> None:
    logger.info("scheduled_job_started", job="price_data")
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Ticker))
            tickers = result.scalars().all()

            for ticker in tickers:
                await ingest_price_data_for_ticker(
                    db=db,
                    symbol=ticker.symbol,
                    period="5d",
                )

            logger.info(
                "scheduled_job_complete",
                job="price_data",
                tickers_processed=len(tickers),
            )
        except Exception as e:
            logger.error("scheduled_job_failed", job="price_data", error=str(e))


async def job_ingest_news() -> None:
    logger.info("scheduled_job_started", job="news")
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Ticker))
            tickers = result.scalars().all()

            for ticker in tickers:
                await ingest_news_for_ticker(
                    db=db,
                    symbol=ticker.symbol,
                )

            logger.info(
                "scheduled_job_complete",
                job="news",
                tickers_processed=len(tickers),
            )
        except Exception as e:
            logger.error("scheduled_job_failed", job="news", error=str(e))


async def job_ingest_filings() -> None:
    logger.info("scheduled_job_started", job="filings")
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Ticker))
            tickers = result.scalars().all()

            for ticker in tickers:
                await ingest_filings_for_ticker(
                    db=db,
                    symbol=ticker.symbol,
                    max_filings=2,
                )

            logger.info(
                "scheduled_job_complete",
                job="filings",
                tickers_processed=len(tickers),
            )
        except Exception as e:
            logger.error("scheduled_job_failed", job="filings", error=str(e))


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        job_ingest_price_data,
        trigger="cron",
        hour=18,
        minute=0,
        id="ingest_price_data",
        replace_existing=True,
    )

    scheduler.add_job(
        job_ingest_news,
        trigger="interval",
        hours=6,
        id="ingest_news",
        replace_existing=True,
    )

    scheduler.add_job(
        job_ingest_filings,
        trigger="cron",
        day_of_week="sun",
        hour=2,
        minute=0,
        id="ingest_filings",
        replace_existing=True,
    )

    scheduler.add_job(
        job_embed_unprocessed_filings,
        trigger="interval",
        hours=1,
        id="embed_unprocessed_filings",
        replace_existing=True,
    )

    logger.info("scheduler_jobs_registered", job_count=4)

async def job_embed_unprocessed_filings() -> None:
    logger.info("scheduled_job_started", job="embed_filings")
    async with AsyncSessionLocal() as db:
        try:
            result = await process_unprocessed_filings(db)
            logger.info(
                "scheduled_job_complete",
                job="embed_filings",
                filings_processed=result["total_filings"],
                chunks_created=result["total_chunks"],
            )
        except Exception as e:
            logger.error(
                "scheduled_job_failed",
                job="embed_filings",
                error=str(e)
            )