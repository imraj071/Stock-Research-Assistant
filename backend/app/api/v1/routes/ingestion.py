from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.models.ticker import Ticker
from app.models.filing import Filing
from app.models.price_data import PriceData
from app.models.news_article import NewsArticle
from app.schemas.ingestion import (
    IngestionRequest,
    IngestionResult,
    TickerResponse,
    TickerStatusResponse,
)
from app.services.ingestion.edgar import ingest_filings_for_ticker
from app.services.ingestion.yfinance_service import ingest_price_data_for_ticker
from app.services.ingestion.news_service import ingest_news_for_ticker
from app.core.logging import logger

router = APIRouter()


@router.post("/ticker/{symbol}", response_model=IngestionResult)
async def ingest_ticker(
    symbol: str,
    request: IngestionRequest = IngestionRequest(),
    db: AsyncSession = Depends(get_db),
) -> IngestionResult:
    symbol = symbol.upper()
    logger.info("manual_ingestion_triggered", symbol=symbol)
    errors = []

    edgar_result = await ingest_filings_for_ticker(
        db=db,
        symbol=symbol,
        max_filings=request.max_filings,
    )

    if not edgar_result["success"]:
        raise HTTPException(
            status_code=400,
            detail=edgar_result.get("error", "EDGAR ingestion failed"),
        )

    price_result = await ingest_price_data_for_ticker(
        db=db,
        symbol=symbol,
        period=request.price_period,
    )

    if not price_result["success"]:
        errors.append(price_result.get("error", "Price ingestion failed"))

    news_result = await ingest_news_for_ticker(
        db=db,
        symbol=symbol,
        page_size=request.news_page_size,
    )

    if not news_result["success"]:
        errors.append(news_result.get("error", "News ingestion failed"))

    return IngestionResult(
        success=True,
        symbol=symbol,
        filings_ingested=edgar_result.get("ingested", 0),
        filings_skipped=edgar_result.get("skipped", 0),
        price_records_ingested=price_result.get("ingested", 0),
        price_records_skipped=price_result.get("skipped", 0),
        news_ingested=news_result.get("ingested", 0),
        news_skipped=news_result.get("skipped", 0),
        errors=errors,
    )


@router.get("/status/{symbol}", response_model=TickerStatusResponse)
async def get_ticker_status(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> TickerStatusResponse:
    symbol = symbol.upper()

    result = await db.execute(
        select(Ticker).where(Ticker.symbol == symbol)
    )
    ticker = result.scalar_one_or_none()

    if ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker {symbol} not found",
        )

    filing_count_result = await db.execute(
        select(func.count()).where(Filing.ticker_id == ticker.id)
    )
    filing_count = filing_count_result.scalar()

    price_count_result = await db.execute(
        select(func.count()).where(PriceData.ticker_id == ticker.id)
    )
    price_count = price_count_result.scalar()

    news_count_result = await db.execute(
        select(func.count()).where(NewsArticle.ticker_id == ticker.id)
    )
    news_count = news_count_result.scalar()

    return TickerStatusResponse(
        ticker=TickerResponse.model_validate(ticker),
        filing_count=filing_count,
        price_record_count=price_count,
        news_article_count=news_count,
    )


@router.get("/tickers", response_model=list[TickerResponse])
async def list_tickers(
    db: AsyncSession = Depends(get_db),
) -> list[TickerResponse]:
    result = await db.execute(select(Ticker).order_by(Ticker.symbol))
    tickers = result.scalars().all()
    return [TickerResponse.model_validate(t) for t in tickers]