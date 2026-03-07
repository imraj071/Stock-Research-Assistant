import cohere
from app.core.config import settings
from app.core.logging import logger
from app.services.rag.retrieval import RetrievedChunk


RERANK_MODEL = "rerank-english-v3.0"
MAX_CHUNKS_TO_RERANK = 20


def get_cohere_client() -> cohere.Client:
    return cohere.Client(api_key=settings.cohere_api_key)


async def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int = 5,
) -> list[RetrievedChunk]:
    if not chunks:
        logger.warning("rerank_called_with_empty_chunks")
        return []

    chunks_to_rerank = chunks[:MAX_CHUNKS_TO_RERANK]

    logger.info(
        "reranking_started",
        query=query[:100],
        chunks_count=len(chunks_to_rerank),
    )

    try:
        client = get_cohere_client()

        documents = [chunk.content for chunk in chunks_to_rerank]

        response = client.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_k,
        )

        reranked = []
        for result in response.results:
            original_chunk = chunks_to_rerank[result.index]
            reranked_chunk = RetrievedChunk(
                chunk_id=original_chunk.chunk_id,
                filing_id=original_chunk.filing_id,
                content=original_chunk.content,
                rrf_score=original_chunk.rrf_score,
                vector_rank=original_chunk.vector_rank,
                bm25_rank=original_chunk.bm25_rank,
            )
            reranked.append(reranked_chunk)

        logger.info(
            "reranking_complete",
            top_k=top_k,
            top_chunk_id=reranked[0].chunk_id if reranked else None,
        )

        return reranked

    except Exception as e:
        logger.error("reranking_failed", error=str(e))
        logger.warning("falling_back_to_rrf_ranking")
        return chunks[:top_k]