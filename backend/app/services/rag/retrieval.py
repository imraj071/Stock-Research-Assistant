from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.logging import logger
from app.services.rag.embeddings import embed_texts


RRF_K = 60
DEFAULT_TOP_K = 20
DEFAULT_FINAL_K = 10


@dataclass
class RetrievedChunk:
    chunk_id: int
    filing_id: int
    content: str
    rrf_score: float
    vector_rank: int | None
    bm25_rank: int | None


async def vector_search(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int = DEFAULT_TOP_K,
    ticker_id: int | None = None,
) -> list[dict]:
    if ticker_id:
        query = text("""
            SELECT
                fc.id,
                fc.filing_id,
                fc.content,
                fc.embedding <=> CAST(:embedding AS vector) AS distance,
                ROW_NUMBER() OVER (
                    ORDER BY fc.embedding <=> CAST(:embedding AS vector)
                ) AS rank
            FROM filing_chunks fc
            JOIN filings f ON fc.filing_id = f.id
            WHERE f.ticker_id = :ticker_id
                AND fc.embedding IS NOT NULL
            ORDER BY distance
            LIMIT :top_k
        """)
        result = await db.execute(
            query,
            {
                "embedding": str(query_embedding),
                "ticker_id": ticker_id,
                "top_k": top_k,
            }
        )
    else:
        query = text("""
            SELECT
                fc.id,
                fc.filing_id,
                fc.content,
                fc.embedding <=> CAST(:embedding AS vector) AS distance,
                ROW_NUMBER() OVER (
                    ORDER BY fc.embedding <=> CAST(:embedding AS vector)
                ) AS rank
            FROM filing_chunks fc
            WHERE fc.embedding IS NOT NULL
            ORDER BY distance
            LIMIT :top_k
        """)
        result = await db.execute(
            query,
            {
                "embedding": str(query_embedding),
                "top_k": top_k,
            }
        )

    rows = result.fetchall()
    return [
        {
            "chunk_id": row.id,
            "filing_id": row.filing_id,
            "content": row.content,
            "rank": row.rank,
        }
        for row in rows
    ]


async def bm25_search(
    db: AsyncSession,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    ticker_id: int | None = None,
) -> list[dict]:
    if ticker_id:
        sql = text("""
            SELECT
                fc.id,
                fc.filing_id,
                fc.content,
                ts_rank(fc.content_tsv, plainto_tsquery('english', :query)) AS score,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(
                        fc.content_tsv, plainto_tsquery('english', :query)
                    ) DESC
                ) AS rank
            FROM filing_chunks fc
            JOIN filings f ON fc.filing_id = f.id
            WHERE f.ticker_id = :ticker_id
                AND fc.content_tsv @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :top_k
        """)
        result = await db.execute(
            sql,
            {
                "query": query,
                "ticker_id": ticker_id,
                "top_k": top_k,
            }
        )
    else:
        sql = text("""
            SELECT
                fc.id,
                fc.filing_id,
                fc.content,
                ts_rank(fc.content_tsv, plainto_tsquery('english', :query)) AS score,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(
                        fc.content_tsv, plainto_tsquery('english', :query)
                    ) DESC
                ) AS rank
            FROM filing_chunks fc
            WHERE fc.content_tsv @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :top_k
        """)
        result = await db.execute(
            sql,
            {
                "query": query,
                "top_k": top_k,
            }
        )

    rows = result.fetchall()
    return [
        {
            "chunk_id": row.id,
            "filing_id": row.filing_id,
            "content": row.content,
            "rank": row.rank,
        }
        for row in rows
    ]


def reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = RRF_K,
) -> list[RetrievedChunk]:
    scores: dict[int, dict] = {}

    for result in vector_results:
        chunk_id = result["chunk_id"]
        rank = result["rank"]
        if chunk_id not in scores:
            scores[chunk_id] = {
                "filing_id": result["filing_id"],
                "content": result["content"],
                "vector_rank": None,
                "bm25_rank": None,
                "rrf_score": 0.0,
            }
        scores[chunk_id]["vector_rank"] = rank
        scores[chunk_id]["rrf_score"] += 1.0 / (k + rank)

    for result in bm25_results:
        chunk_id = result["chunk_id"]
        rank = result["rank"]
        if chunk_id not in scores:
            scores[chunk_id] = {
                "filing_id": result["filing_id"],
                "content": result["content"],
                "vector_rank": None,
                "bm25_rank": None,
                "rrf_score": 0.0,
            }
        scores[chunk_id]["bm25_rank"] = rank
        scores[chunk_id]["rrf_score"] += 1.0 / (k + rank)

    ranked = sorted(
        scores.items(),
        key=lambda x: x[1]["rrf_score"],
        reverse=True,
    )

    return [
        RetrievedChunk(
            chunk_id=chunk_id,
            filing_id=data["filing_id"],
            content=data["content"],
            rrf_score=data["rrf_score"],
            vector_rank=data["vector_rank"],
            bm25_rank=data["bm25_rank"],
        )
        for chunk_id, data in ranked
    ]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    top_k: int = DEFAULT_FINAL_K,
    ticker_id: int | None = None,
) -> list[RetrievedChunk]:
    logger.info(
        "hybrid_search_started",
        query=query[:100],
        ticker_id=ticker_id,
        top_k=top_k,
    )

    query_embeddings = await embed_texts([query])
    query_embedding = query_embeddings[0]

    vector_results = await vector_search(
        db, query_embedding, top_k=DEFAULT_TOP_K, ticker_id=ticker_id
    )
    bm25_results = await bm25_search(
        db, query, top_k=DEFAULT_TOP_K, ticker_id=ticker_id
    )

    logger.info(
        "search_results_raw",
        vector_count=len(vector_results),
        bm25_count=len(bm25_results),
    )

    fused_results = reciprocal_rank_fusion(vector_results, bm25_results)
    final_results = fused_results[:top_k]

    logger.info(
        "hybrid_search_complete",
        final_count=len(final_results),
        top_rrf_score=final_results[0].rrf_score if final_results else 0,
    )

    return final_results