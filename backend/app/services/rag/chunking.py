import re
from dataclasses import dataclass
from app.core.logging import logger


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    token_count: int


def estimate_token_count(text: str) -> int:
    return len(text) // 4


def split_into_sections(text: str) -> list[str]:
    section_pattern = re.compile(
        r'\n(?='
        r'(?:ITEM\s+\d+[A-Z]?\.)'
        r'|(?:Item\s+\d+[A-Z]?\.)'
        r'|(?:[A-Z][A-Z\s]{10,}(?:\n|$))'
        r')',
        re.MULTILINE
    )

    sections = section_pattern.split(text)
    sections = [s.strip() for s in sections if s.strip()]

    if not sections:
        return [text]

    return sections


def split_into_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    return paragraphs


def split_into_sentences(text: str) -> list[str]:
    sentence_pattern = re.compile(
        r'(?<=[.!?])\s+(?=[A-Z])'
    )
    sentences = sentence_pattern.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def merge_small_chunks(
    chunks: list[str],
    min_tokens: int = 100,
) -> list[str]:
    merged = []
    buffer = ""

    for chunk in chunks:
        if estimate_token_count(buffer + " " + chunk) < min_tokens:
            buffer = (buffer + " " + chunk).strip()
        else:
            if buffer:
                merged.append(buffer)
            buffer = chunk

    if buffer:
        merged.append(buffer)

    return merged


def chunk_financial_document(
    text: str,
    max_tokens: int = 512,
    min_tokens: int = 100,
    overlap_tokens: int = 50,
) -> list[TextChunk]:
    if not text or not text.strip():
        logger.warning("empty_text_received_for_chunking")
        return []

    sections = split_into_sections(text)
    raw_chunks = []

    for section in sections:
        section_tokens = estimate_token_count(section)

        if section_tokens <= max_tokens:
            raw_chunks.append(section)
            continue

        paragraphs = split_into_paragraphs(section)

        for paragraph in paragraphs:
            para_tokens = estimate_token_count(paragraph)

            if para_tokens <= max_tokens:
                raw_chunks.append(paragraph)
                continue

            sentences = split_into_sentences(paragraph)
            current_chunk = ""

            for sentence in sentences:
                candidate = (current_chunk + " " + sentence).strip()
                if estimate_token_count(candidate) <= max_tokens:
                    current_chunk = candidate
                else:
                    if current_chunk:
                        raw_chunks.append(current_chunk)
                    current_chunk = sentence

            if current_chunk:
                raw_chunks.append(current_chunk)

    merged_chunks = merge_small_chunks(raw_chunks, min_tokens)

    final_chunks = []
    for i, content in enumerate(merged_chunks):
        if overlap_tokens > 0 and i > 0:
            prev_content = merged_chunks[i - 1]
            prev_words = prev_content.split()
            overlap_word_count = overlap_tokens * 4 // 5
            overlap_text = " ".join(prev_words[-overlap_word_count:])
            content = overlap_text + " " + content

        final_chunks.append(
            TextChunk(
                content=content.strip(),
                chunk_index=i,
                token_count=estimate_token_count(content),
            )
        )

    logger.info(
        "document_chunked",
        total_chunks=len(final_chunks),
        avg_tokens=sum(c.token_count for c in final_chunks) // max(len(final_chunks), 1),
    )

    return final_chunks