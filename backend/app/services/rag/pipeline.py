from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.services.rag.retrieval import hybrid_search, RetrievedChunk
from app.services.rag.reranker import rerank_chunks


async def retrieve_relevant_chunks(
    db: AsyncSession,
    query: str,
    ticker_id: int | None = None,
    hybrid_top_k: int = 20,
    final_top_k: int = 5,
) -> list[RetrievedChunk]:
    logger.info(
        "rag_pipeline_started",
        query=query[:100],
        ticker_id=ticker_id,
    )

    hybrid_results = await hybrid_search(
        db=db,
        query=query,
        top_k=hybrid_top_k,
        ticker_id=ticker_id,
    )

    if not hybrid_results:
        logger.warning("no_hybrid_results_found", query=query[:100])
        return []

    reranked_results = await rerank_chunks(
        query=query,
        chunks=hybrid_results,
        top_k=final_top_k,
    )

    logger.info(
        "rag_pipeline_complete",
        hybrid_count=len(hybrid_results),
        final_count=len(reranked_results),
    )

    return reranked_results