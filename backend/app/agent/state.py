from typing import Annotated
from dataclasses import dataclass, field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


@dataclass
class ResearchContext:
    ticker: str
    ticker_id: int | None = None
    company_name: str | None = None


@dataclass
class FilingContext:
    filing_id: int
    doc_type: str
    content: str
    chunk_id: int
    relevance_score: float


@dataclass
class PriceContext:
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass
class NewsContext:
    title: str
    source: str | None
    published_at: str | None
    description: str | None
    url: str


class AgentState(dict):
    messages: Annotated[list[BaseMessage], add_messages]
    research_context: ResearchContext | None
    filing_chunks: list[FilingContext]
    price_data: list[PriceContext]
    news_articles: list[NewsContext]
    research_query: str
    report: str | None
    error: str | None
    iteration_count: int