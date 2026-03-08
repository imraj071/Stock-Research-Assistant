import json
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.ticker import Ticker
from app.agent.graph import run_agent, create_agent_graph
from app.schemas.agent import AgentRequest, AgentResponse, StreamEvent
from app.core.logging import logger
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig
from app.api.v1.routes.dependencies import get_current_user
from app.models.user import User

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


def make_sse_event(event_type: str, data: dict) -> str:
    event = StreamEvent(
        event_type=event_type,
        data=data,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return f"data: {event.model_dump_json()}\n\n"


@router.post("/research", response_model=AgentResponse)
@limiter.limit("10/hour")
async def run_research(
    request: Request,
    body: AgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentResponse:
    ticker_symbol = body.ticker_symbol.upper()

    result = await db.execute(
        select(Ticker).where(Ticker.symbol == ticker_symbol)
    )
    ticker = result.scalar_one_or_none()

    if ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker {ticker_symbol} not found. Run ingestion first.",
        )

    logger.info(
        "research_request_received",
        ticker=ticker_symbol,
        query=body.query[:100],
        user_id=current_user.id,
    )

    result = await run_agent(
        db=db,
        query=body.query,
        ticker_symbol=ticker_symbol,
    )

    return AgentResponse(
        success=result["success"],
        ticker=result["ticker"],
        query=result["query"],
        report=result["report"],
        iterations=result["iterations"],
        error=result.get("error"),
    )

@router.post("/research/stream")
@limiter.limit("10/hour")
async def stream_research(
    request: Request,
    body: AgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    ticker_symbol = body.ticker_symbol.upper()
    
    result = await db.execute(
        select(Ticker).where(Ticker.symbol == ticker_symbol)
    )
    ticker = result.scalar_one_or_none()

    if ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker {ticker_symbol} not found. Run ingestion first.",
        )

    async def event_generator():
        try:
            yield make_sse_event("research_started", {
                "ticker": ticker_symbol,
                "query": body.query,
            })

            graph = create_agent_graph(db)

            initial_state = {
                "messages": [HumanMessage(
                    content=f"Research question: {request.query}\nTicker: {ticker_symbol}"
                )],
                "research_context": {"ticker": ticker_symbol},
                "filing_chunks": [],
                "price_data": [],
                "news_articles": [],
                "research_query": body.query,
                "report": None,
                "error": None,
                "iteration_count": 0,
            }

            config = RunnableConfig(
                run_name=f"research_{ticker_symbol}_{request.query[:30]}",
                tags=[ticker_symbol, "research"],
                metadata={
                    "ticker": ticker_symbol,
                    "query": body.query,
                    "user_id": current_user.id,
                }
            )

            async for event in graph.astream_events(
                initial_state,
                config=config,
                version="v2",
            ):
                event_name = event.get("event", "")
                event_data = event.get("data", {})

                if event_name == "on_tool_start":
                    tool_name = event.get("name", "unknown_tool")
                    tool_input = event_data.get("input", {})
                    yield make_sse_event("tool_started", {
                        "tool": tool_name,
                        "input": tool_input,
                    })

                elif event_name == "on_tool_end":
                    tool_name = event.get("name", "unknown_tool")
                    yield make_sse_event("tool_completed", {
                        "tool": tool_name,
                    })

                elif event_name == "on_chat_model_stream":
                    chunk = event_data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield make_sse_event("llm_token", {
                            "token": chunk.content,
                        })

                elif event_name == "on_chain_end":
                    output = event_data.get("output", {})
                    if isinstance(output, dict) and output.get("report"):
                        yield make_sse_event("report_complete", {
                            "report": output["report"],
                            "iterations": output.get("iteration_count", 0),
                        })

            yield make_sse_event("research_complete", {
                "ticker": ticker_symbol,
            })

        except Exception as e:
            logger.error("streaming_failed", error=str(e))
            yield make_sse_event("error", {
                "message": str(e),
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )