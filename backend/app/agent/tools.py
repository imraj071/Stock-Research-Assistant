import json
from datetime import date
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ticker import Ticker
from app.models.price_data import PriceData
from app.models.news_article import NewsArticle
from app.services.rag.pipeline import retrieve_relevant_chunks
from app.core.logging import logger


def get_agent_tools(db: AsyncSession) -> list:
    @tool
    async def search_filings(query: str, ticker_symbol: str) -> str:
        """
        Search SEC filings for a ticker using semantic and keyword search.
        Use this to find information about company financials, risk factors,
        business operations, and management discussion from 10-K and 10-Q filings.

        Args:
            query: The specific question or topic to search for
            ticker_symbol: The stock ticker symbol e.g. AAPL
        """
        logger.info("tool_search_filings", query=query[:100], ticker=ticker_symbol)

        try:
            result = await db.execute(
                select(Ticker).where(Ticker.symbol == ticker_symbol.upper())
            )
            ticker = result.scalar_one_or_none()

            if ticker is None:
                return json.dumps({
                    "error": f"Ticker {ticker_symbol} not found in database",
                    "chunks": [],
                })

            chunks = await retrieve_relevant_chunks(
                db=db,
                query=query,
                ticker_id=ticker.id,
                final_top_k=5,
            )

            return json.dumps({
                "ticker": ticker_symbol,
                "query": query,
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "filing_id": c.filing_id,
                        "content": c.content,
                        "relevance_score": c.rrf_score,
                    }
                    for c in chunks
                ],
            })

        except Exception as e:
            logger.error("tool_search_filings_failed", error=str(e))
            return json.dumps({"error": str(e), "chunks": []})


    @tool
    async def get_price_data(ticker_symbol: str, limit: int = 30) -> str:
        """
        Get recent historical price data for a ticker including
        open, high, low, close and volume. Use this to understand
        recent price performance and trading activity.

        Args:
            ticker_symbol: The stock ticker symbol e.g. AAPL
            limit: Number of most recent trading days to return (default 30)
        """
        logger.info("tool_get_price_data", ticker=ticker_symbol, limit=limit)
        limit = int(limit)

        try:
            result = await db.execute(
                select(Ticker).where(Ticker.symbol == ticker_symbol.upper())
            )
            ticker = result.scalar_one_or_none()

            if ticker is None:
                return json.dumps({
                    "error": f"Ticker {ticker_symbol} not found in database",
                    "price_data": [],
                })

            price_result = await db.execute(
                select(PriceData)
                .where(PriceData.ticker_id == ticker.id)
                .order_by(PriceData.date.desc())
                .limit(limit)
            )
            prices = price_result.scalars().all()

            return json.dumps({
                "ticker": ticker_symbol,
                "price_data": [
                    {
                        "date": str(p.date),
                        "open": p.open,
                        "high": p.high,
                        "low": p.low,
                        "close": p.close,
                        "volume": p.volume,
                    }
                    for p in prices
                ],
            })

        except Exception as e:
            logger.error("tool_get_price_data_failed", error=str(e))
            return json.dumps({"error": str(e), "price_data": []})


    @tool
    async def search_news(ticker_symbol: str, limit: int = 10) -> str:
        """
        Get recent news articles for a ticker. Use this to understand
        recent developments, market sentiment, and events affecting
        the company.

        Args:
            ticker_symbol: The stock ticker symbol e.g. AAPL
            limit: Number of most recent articles to return (default 10)
        """
        logger.info("tool_search_news", ticker=ticker_symbol, limit=limit)
        limit = int(limit)
        
        try:
            result = await db.execute(
                select(Ticker).where(Ticker.symbol == ticker_symbol.upper())
            )
            ticker = result.scalar_one_or_none()

            if ticker is None:
                return json.dumps({
                    "error": f"Ticker {ticker_symbol} not found in database",
                    "articles": [],
                })

            news_result = await db.execute(
                select(NewsArticle)
                .where(NewsArticle.ticker_id == ticker.id)
                .order_by(NewsArticle.published_at.desc())
                .limit(limit)
            )
            articles = news_result.scalars().all()

            return json.dumps({
                "ticker": ticker_symbol,
                "articles": [
                    {
                        "title": a.title,
                        "source": a.source,
                        "published_at": str(a.published_at) if a.published_at else None,
                        "description": a.description,
                        "url": a.url,
                    }
                    for a in articles
                ],
            })

        except Exception as e:
            logger.error("tool_search_news_failed", error=str(e))
            return json.dumps({"error": str(e), "articles": []})


    @tool
    async def generate_report(
        ticker_symbol: str,
        research_question: str,
    ) -> str:
        """
        Signal that enough context has been gathered and a report
        should be generated. Call this ONLY after you have already
        called search_filings, get_price_data, and search_news.
        This tool does not generate the report itself — it signals
        the graph to move to the report generation node.

        Args:
            ticker_symbol: The stock ticker symbol e.g. AAPL
            research_question: The original research question being answered
        """
        logger.info(
            "tool_generate_report_called",
            ticker=ticker_symbol,
            question=research_question[:100],
        )
        return json.dumps({
            "ticker": ticker_symbol,
            "research_question": research_question,
            "signal": "GENERATE_REPORT",
        })

    return [search_filings, get_price_data, search_news, generate_report]