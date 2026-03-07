from datetime import datetime, timezone
from newsapi import NewsApiClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ticker import Ticker
from app.models.news_article import NewsArticle
from app.core.config import settings
from app.core.logging import logger


def get_newsapi_client() -> NewsApiClient:
    return NewsApiClient(api_key=settings.news_api_key)


async def fetch_news_for_symbol(
    symbol: str,
    company_name: str,
    page_size: int = 20,
) -> list[dict]:
    try:
        client = get_newsapi_client()

        query = f'"{company_name}" OR "{symbol}"'

        response = client.get_everything(
            q=query,
            language="en",
            sort_by="publishedAt",
            page_size=page_size,
        )

        if response.get("status") != "ok":
            logger.error(
                "newsapi_request_failed",
                symbol=symbol,
                status=response.get("status"),
            )
            return []

        articles = response.get("articles", [])
        results = []

        for article in articles:
            source = article.get("source", {})
            published_at = article.get("publishedAt")

            parsed_date = None
            if published_at:
                try:
                    parsed_date = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    )
                except ValueError:
                    parsed_date = None

            results.append({
                "title": article.get("title", "")[:500],
                "description": article.get("description"),
                "content": article.get("content"),
                "url": article.get("url", ""),
                "source": source.get("name"),
                "published_at": parsed_date,
            })

        logger.info(
            "news_fetched",
            symbol=symbol,
            count=len(results),
        )
        return results

    except Exception as e:
        logger.error("news_fetch_failed", symbol=symbol, error=str(e))
        return []


async def ingest_news_for_ticker(
    db: AsyncSession,
    symbol: str,
    page_size: int = 20,
) -> dict:
    logger.info("news_ingestion_started", symbol=symbol)

    result = await db.execute(
        select(Ticker).where(Ticker.symbol == symbol.upper())
    )
    ticker = result.scalar_one_or_none()

    if ticker is None:
        logger.error("ticker_not_found_for_news_ingestion", symbol=symbol)
        return {
            "success": False,
            "error": f"Ticker {symbol} not found. Run EDGAR ingestion first.",
        }

    articles = await fetch_news_for_symbol(
        symbol=symbol,
        company_name=ticker.company_name,
        page_size=page_size,
    )

    ingested = 0
    skipped = 0

    for article in articles:
        if not article["url"]:
            skipped += 1
            continue

        existing = await db.execute(
            select(NewsArticle).where(
                NewsArticle.ticker_id == ticker.id,
                NewsArticle.url == article["url"],
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        news_row = NewsArticle(
            ticker_id=ticker.id,
            title=article["title"],
            description=article["description"],
            content=article["content"],
            url=article["url"],
            source=article["source"],
            published_at=article["published_at"],
        )
        db.add(news_row)
        ingested += 1

    await db.commit()

    logger.info(
        "news_ingestion_complete",
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