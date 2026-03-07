import asyncio
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.logging import logger
from app.models.filing import Filing
from app.models.filing_chunk import FilingChunk
from app.services.rag.chunking import chunk_financial_document

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384
BATCH_SIZE = 64


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    logger.info("loading_embedding_model", model=EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info("embedding_model_loaded", model=EMBEDDING_MODEL)
    return model


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return embeddings.tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_texts_sync, texts)


async def process_filing(
    db: AsyncSession,
    filing: Filing,
) -> dict:
    logger.info(
        "processing_filing",
        filing_id=filing.id,
        doc_type=filing.doc_type,
    )

    if not filing.raw_text:
        logger.warning("filing_has_no_raw_text", filing_id=filing.id)
        filing.is_chunked = True
        await db.commit()
        return {"filing_id": filing.id, "chunks_created": 0}

    chunks = chunk_financial_document(filing.raw_text)

    if not chunks:
        logger.warning("no_chunks_produced", filing_id=filing.id)
        filing.is_chunked = True
        await db.commit()
        return {"filing_id": filing.id, "chunks_created": 0}

    texts = [chunk.content for chunk in chunks]
    embeddings = await embed_texts(texts)

    for chunk, embedding in zip(chunks, embeddings):
        filing_chunk = FilingChunk(
            filing_id=filing.id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=embedding,
            token_count=chunk.token_count,
        )
        db.add(filing_chunk)

    filing.is_chunked = True
    await db.commit()

    logger.info(
        "filing_processed",
        filing_id=filing.id,
        chunks_created=len(chunks),
    )

    return {
        "filing_id": filing.id,
        "chunks_created": len(chunks),
    }


async def process_unprocessed_filings(
    db: AsyncSession,
) -> dict:
    logger.info("embedding_pipeline_started")

    result = await db.execute(
        select(Filing).where(Filing.is_chunked == False)
    )
    filings = result.scalars().all()

    if not filings:
        logger.info("no_unprocessed_filings_found")
        return {"total_filings": 0, "total_chunks": 0}

    logger.info("unprocessed_filings_found", count=len(filings))

    total_chunks = 0
    for filing in filings:
        result = await process_filing(db, filing)
        total_chunks += result["chunks_created"]

    logger.info(
        "embedding_pipeline_complete",
        filings_processed=len(filings),
        total_chunks=total_chunks,
    )

    return {
        "total_filings": len(filings),
        "total_chunks": total_chunks,
    }