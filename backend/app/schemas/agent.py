from pydantic import BaseModel
from datetime import datetime


class AgentRequest(BaseModel):
    query: str
    ticker_symbol: str


class AgentResponse(BaseModel):
    success: bool
    ticker: str
    query: str
    report: str | None
    iterations: int
    error: str | None = None


class StreamEvent(BaseModel):
    event_type: str
    data: dict
    timestamp: str