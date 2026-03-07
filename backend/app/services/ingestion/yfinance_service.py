import asyncio
import requests
from datetime import date, datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ticker import Ticker
from app.models.price_data import PriceData
from app.core.logging import logger

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _fetch_company_info_sync(symbol: str) -> dict | None:
    session = _get_session()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})

        return {
            "company_name": meta.get("longName") or meta.get("shortName") or symbol,
            "sector": None,
            "industry": None,
            "market_cap": None,
        }

    except Exception as e:
        logger.error("company_info_fetch_failed", symbol=symbol, error=str(e))
        return None


def _fetch_price_history_sync(symbol: str, period: str) -> list[dict]:
    session = _get_session()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={period}&interval=1d"

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        chart = data.get("chart", {}).get("result", [])
        if not chart:
            return []

        timestamps = chart[0].get("timestamp", [])
        indicators = chart[0].get("indicators", {})
        quotes = indicators.get("quote", [{}])[0]

        opens = quotes.get("open", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        closes = quotes.get("close", [])
        volumes = quotes.get("volume", [])

        records = []
        for i, ts in enumerate(timestamps):
            records.append({
                "date": datetime.fromtimestamp(ts).date(),
                "open": float(opens[i]) if i < len(opens) and opens[i] is not None else None,
                "high": float(highs[i]) if i < len(highs) and highs[i] is not None else None,
                "low": float(lows[i]) if i < len(lows) and lows[i] is not None else None,
                "close": float(closes[i]) if i < len(closes) and closes[i] is not None else None,
                "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
            })

        return records

    except Exception as e:
        logger.error("price_history_fetch_failed", symbol=symbol, error=str(e))
        return []


async def fetch_company_info(symbol: str) -> dict | None:
    try:
        result = await asyncio.to_thread(_fetch_company_info_sync, symbol)
        logger.info("company_info_fetched", symbol=symbol)
        return result
    except Exception as e:
        logger.error("company_info_fetch_failed", symbol=symbol, error=str(e))
        return None


async def fetch_price_history(
    symbol: str,
    period: str = "1y",
) -> list[dict]:
    try:
        records = await asyncio.to_thread(_fetch_price_history_sync, symbol, period)
        if not records:
            logger.warning("price_history_empty", symbol=symbol)
            return []
        logger.info("price_history_fetched", symbol=symbol, records=len(records))
        return records
    except Exception as e:
        logger.error("price_history_fetch_failed", symbol=symbol, error=str(e))
        return []


async def ingest_price_data_for_ticker(
    db: AsyncSession,
    symbol: str,
    period: str = "1y",
) -> dict:
    logger.info("price_ingestion_started", symbol=symbol)

    result = await db.execute(
        select(Ticker).where(Ticker.symbol == symbol.upper())
    )
    ticker = result.scalar_one_or_none()

    if ticker is None:
        logger.error("ticker_not_found_for_price_ingestion", symbol=symbol)
        return {
            "success": False,
            "error": f"Ticker {symbol} not found. Run EDGAR ingestion first.",
        }

    company_info = await fetch_company_info(symbol)
    if company_info:
        ticker.company_name = company_info["company_name"] or ticker.company_name
        ticker.sector = company_info["sector"] or ticker.sector
        ticker.industry = company_info["industry"] or ticker.industry
        ticker.market_cap = company_info["market_cap"] or ticker.market_cap
        await db.commit()
        logger.info("ticker_metadata_updated", symbol=symbol)

    price_records = await fetch_price_history(symbol, period)

    ingested = 0
    skipped = 0

    for record in price_records:
        existing = await db.execute(
            select(PriceData).where(
                PriceData.ticker_id == ticker.id,
                PriceData.date == record["date"],
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        price_row = PriceData(
            ticker_id=ticker.id,
            date=record["date"],
            open=record["open"],
            high=record["high"],
            low=record["low"],
            close=record["close"],
            volume=record["volume"],
        )
        db.add(price_row)
        ingested += 1

    await db.commit()

    logger.info(
        "price_ingestion_complete",
        symbol=symbol,
        ingested=ingested,
        skipped=skipped,
    )

    return {
        "success": True,
        "symbol": symbol,
        "ingested": ingested,
        "skipped": skipped,
    }