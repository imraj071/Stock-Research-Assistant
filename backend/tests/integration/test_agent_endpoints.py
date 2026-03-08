import pytest
from unittest.mock import patch, AsyncMock


class TestAgentEndpoint:
    async def test_research_requires_auth(self, client):
        response = await client.post(
            "/api/v1/agent/research",
            json={"query": "What are the risks?", "ticker_symbol": "AAPL"},
        )
        assert response.status_code == 403

    async def test_research_ticker_not_found(self, client, auth_headers):
        response = await client.post(
            "/api/v1/agent/research",
            json={"query": "What are the risks?", "ticker_symbol": "FAKE"},
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_research_success_mocked(self, client, auth_headers, db):
        from app.models.ticker import Ticker
        ticker = Ticker(
            symbol="TEST",
            company_name="Test Company",
        )
        db.add(ticker)
        await db.commit()

        mock_result = {
            "success": True,
            "ticker": "TEST",
            "query": "What are the risks?",
            "report": "This is a test report.",
            "iterations": 2,
            "error": None,
        }

        with patch(
            "app.api.v1.routes.agent.run_agent",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                "/api/v1/agent/research",
                json={"query": "What are the risks?", "ticker_symbol": "TEST"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["report"] == "This is a test report."
        assert data["iterations"] == 2

    async def test_research_missing_query(self, client, auth_headers):
        response = await client.post(
            "/api/v1/agent/research",
            json={"ticker_symbol": "AAPL"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_research_missing_ticker(self, client, auth_headers):
        response = await client.post(
            "/api/v1/agent/research",
            json={"query": "What are the risks?"},
            headers=auth_headers,
        )
        assert response.status_code == 422