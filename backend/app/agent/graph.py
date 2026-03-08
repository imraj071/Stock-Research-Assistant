import json
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.agent.state import AgentState
from app.agent.tools import get_agent_tools
from app.agent.prompts import SYSTEM_PROMPT, REPORT_PROMPT
from langchain_core.runnables.config import RunnableConfig

MAX_ITERATIONS = 10


def get_llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=settings.groq_api_key,
        temperature=0,
    )


def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    iteration_count = state.get("iteration_count", 0)

    if iteration_count >= MAX_ITERATIONS:
        logger.warning("max_iterations_reached", iterations=iteration_count)
        return "generate_report"

    if state.get("error"):
        return END

    last_message = messages[-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END

    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "generate_report":
            return "generate_report"

    return "tools"


async def agent_node(state: AgentState, db: AsyncSession) -> dict:
    logger.info(
        "agent_node_called",
        iteration=state.get("iteration_count", 0),
        message_count=len(state["messages"]),
    )

    llm = get_llm()
    tools = get_agent_tools(db)
    llm_with_tools = llm.bind_tools(tools)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"],
    ]

    response = await llm_with_tools.ainvoke(messages)

    return {
        "messages": [response],
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


async def tools_node(state: AgentState, db: AsyncSession) -> dict:
    tools = get_agent_tools(db)
    tool_node = ToolNode(tools)
    result = await tool_node.ainvoke(state)
    return result


async def generate_report_node(state: AgentState, db: AsyncSession) -> dict:
    logger.info("generate_report_node_called")

    filing_chunks = []
    price_data = []
    news_articles = []

    for message in state["messages"]:
        if isinstance(message, ToolMessage):
            try:
                data = json.loads(message.content)

                if "chunks" in data:
                    for chunk in data.get("chunks", []):
                        filing_chunks.append(
                            f"[Filing {chunk.get('filing_id')}] {chunk.get('content', '')[:500]}"
                        )

                if "price_data" in data:
                    for price in data.get("price_data", [])[:10]:
                        price_data.append(
                            f"{price.get('date')}: Close ${price.get('close', 'N/A'):.2f} "
                            f"Volume {price.get('volume', 'N/A'):,.0f}"
                        )

                if "articles" in data:
                    for article in data.get("articles", []):
                        news_articles.append(
                            f"[{article.get('source')}] {article.get('title')} "
                            f"({article.get('published_at', '')[:10]})"
                        )

            except (json.JSONDecodeError, TypeError):
                continue

    research_question = state.get("research_query", "General company research")
    ticker = state.get("research_context", {})
    ticker_symbol = ticker.get("ticker", "Unknown") if isinstance(ticker, dict) else getattr(ticker, "ticker", "Unknown")

    report_prompt = REPORT_PROMPT.format(
        research_question=research_question,
        ticker=ticker_symbol,
        filing_context="\n\n".join(filing_chunks) if filing_chunks else "No filing data retrieved",
        price_context="\n".join(price_data) if price_data else "No price data retrieved",
        news_context="\n".join(news_articles) if news_articles else "No news retrieved",
    )

    llm = get_llm()
    response = await llm.ainvoke([HumanMessage(content=report_prompt)])

    logger.info("report_generated", length=len(response.content))

    return {
        "report": response.content,
        "messages": [response],
    }


def create_agent_graph(db: AsyncSession) -> StateGraph:
    async def _agent_node(state: AgentState) -> dict:
        return await agent_node(state, db)

    async def _tools_node(state: AgentState) -> dict:
        return await tools_node(state, db)

    async def _generate_report_node(state: AgentState) -> dict:
        return await generate_report_node(state, db)

    graph = StateGraph(AgentState)

    graph.add_node("agent", _agent_node)
    graph.add_node("tools", _tools_node)
    graph.add_node("generate_report", _generate_report_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "generate_report": "generate_report",
            END: END,
        }
    )

    graph.add_edge("tools", "agent")
    graph.add_edge("generate_report", END)

    return graph.compile()


async def run_agent(
    db: AsyncSession,
    query: str,
    ticker_symbol: str,
) -> dict:
    logger.info("agent_run_started", query=query[:100], ticker=ticker_symbol)

    graph = create_agent_graph(db)

    initial_state = {
        "messages": [HumanMessage(content=f"Research question: {query}\nTicker: {ticker_symbol}")],
        "research_context": {"ticker": ticker_symbol},
        "filing_chunks": [],
        "price_data": [],
        "news_articles": [],
        "research_query": query,
        "report": None,
        "error": None,
        "iteration_count": 0,
    }

    config = RunnableConfig(
        run_name=f"research_{ticker_symbol}_{query[:30]}",
        tags=[ticker_symbol, "research"],
        metadata={
            "ticker": ticker_symbol,
            "query": query,
        }
    )

    try:
        final_state = await graph.ainvoke(initial_state, config=config)

        logger.info(
            "agent_run_complete",
            ticker=ticker_symbol,
            iterations=final_state.get("iteration_count", 0),
            report_length=len(final_state.get("report", "") or ""),
        )

        return {
            "success": True,
            "ticker": ticker_symbol,
            "query": query,
            "report": final_state.get("report"),
            "iterations": final_state.get("iteration_count", 0),
        }

    except Exception as e:
        logger.error("agent_run_failed", error=str(e))
        return {
            "success": False,
            "ticker": ticker_symbol,
            "query": query,
            "report": None,
            "iterations": 0,
            "error": str(e),
        }