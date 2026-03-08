from pydantic import BaseModel, ConfigDict
from datetime import datetime


class IngestionRequest(BaseModel):
    max_filings: int = 5
    price_period: str = "1y"
    news_page_size: int = 20


class IngestionResult(BaseModel):
    success: bool
    symbol: str
    filings_ingested: int = 0
    filings_skipped: int = 0
    price_records_ingested: int = 0
    price_records_skipped: int = 0
    news_ingested: int = 0
    news_skipped: int = 0
    errors: list[str] = []


class TickerResponse(BaseModel):
    id: int
    symbol: str
    company_name: str
    sector: str | None
    industry: str | None
    market_cap: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TickerStatusResponse(BaseModel):
    ticker: TickerResponse
    filing_count: int
    price_record_count: int
    news_article_count: int