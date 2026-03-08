import pytest
from sqlalchemy import text
from app.services.rag.chunking import (
    TextChunk,
    estimate_token_count,
    split_into_sentences,
    chunk_financial_document,
)


class TestTokenCounting:
    def test_count_tokens_empty_string(self):
        assert estimate_token_count("") == 0

    def test_count_tokens_basic(self):
        result = estimate_token_count("hello world")
        assert result > 0

    def test_count_tokens_longer_text_more_tokens(self):
        short = estimate_token_count("hello")
        long = estimate_token_count("hello world this is a longer sentence")
        assert long > short

    def test_count_tokens_approximation(self):
        text = "a" * 400
        result = estimate_token_count(text)
        assert 90 <= result <= 110


class TestSentenceSplitting:
    def test_split_basic_sentences(self):
        text = "This is sentence one. This is sentence two. This is sentence three."
        result = split_into_sentences(text)
        assert len(result) >= 2

    def test_split_empty_string(self):
        result = split_into_sentences("")
        assert result == [] or result == [""]

    def test_split_single_sentence(self):
        text = "This is a single sentence without a period"
        result = split_into_sentences(text)
        assert len(result) >= 1

    def test_split_preserves_content(self):
        text = "Apple reported revenue. Earnings were strong."
        result = split_into_sentences(text)
        combined = " ".join(result)
        assert "Apple" in combined
        assert "Earnings" in combined


class TestChunkDocument:
    def test_chunk_empty_document(self):
        result = chunk_financial_document("")
        assert result == []

    def test_chunk_short_document_single_chunk(self):
        text = "This is a short document about Apple Inc financials."
        result = chunk_financial_document(text)
        assert len(result) >= 1

    def test_chunk_returns_list_of_strings(self):
        text = "Apple Inc reported strong quarterly results. " * 20
        result = chunk_financial_document(text)
        assert isinstance(result, list)
        assert all(isinstance(c, TextChunk) for c in result)

    def test_chunk_long_document_multiple_chunks(self):
        text = "Apple reported strong revenue growth this quarter. " * 100
        result = chunk_financial_document(text)
        assert len(result) > 1

    def test_chunk_max_size_respected(self):
        text = "Apple reported strong revenue growth this quarter. " * 100
        result = chunk_financial_document(text, max_tokens=200)
        for chunk in result:
            assert estimate_token_count(chunk.content) <= 300

    def test_chunk_no_empty_chunks(self):
        text = "Apple reported strong revenue growth. " * 50
        result = chunk_financial_document(text)
        assert all(len(c.content.strip()) > 0 for c in result)

    def test_chunk_preserves_all_content(self):
        text = "ITEM 1. BUSINESS\nApple designs iPhones. " * 10
        result = chunk_financial_document(text)
        combined = " ".join(c.content for c in result)
        assert "Apple" in combined
        assert "iPhone" in combined

    def test_chunk_sec_headers_create_boundaries(self):
        text = (
        "ITEM 1. BUSINESS\n"
        "Apple is a technology company. " * 20 +
        "\nITEM 1A. RISK FACTORS\n"
        "The company faces competition. " * 20
        )
        result = chunk_financial_document(text)
        assert len(result) >= 2