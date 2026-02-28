# 📈 Stock Research Assistant

> **AI-powered financial research platform** — Ingest SEC filings, synthesize earnings transcripts, and generate deep-dive research reports through a multi-step agentic pipeline backed by hybrid RAG retrieval.

---

## ⚡ Overview

Stock Research Assistant is a **production-grade full-stack application** that combines Agentic AI and Retrieval-Augmented Generation (RAG) to automate financial research. Users can query any publicly traded company and receive synthesized research reports grounded in real SEC filings, earnings call transcripts, price data, and financial news — with every claim traceable back to its source.

Built with a focus on **observability, reliability, and correctness** over surface-level demos.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        React Frontend                       │
│           TypeScript · TanStack Query · Tailwind CSS        │
│              SSE Streaming · LangSmith Trace View           │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP / SSE
┌─────────────────────▼───────────────────────────────────────┐
│                      FastAPI Backend                        │
│         Async SQLAlchemy · JWT Auth · slowapi               │
│              APScheduler · structlog · Alembic              │
└──────┬──────────────┬──────────────────┬────────────────────┘
       │              │                  │
┌──────▼──────┐ ┌─────▼──────┐ ┌────────▼───────┐
│  PostgreSQL │ │   Redis    │ │  LangGraph     │
│  + pgvector │ │            │ │  Agent Layer   │
│  BM25 Search│ │            │ │  + LangSmith   │
└─────────────┘ └────────────┘ └────────────────┘
```

---

## 🧠 AI & RAG Pipeline

| Layer | Technology | Purpose |
|---|---|---|
| Embeddings | `text-embedding-3-small` | Chunk vectorization |
| Vector Search | pgvector (dense) | Semantic retrieval |
| Keyword Search | BM25 via pg_search (sparse) | Lexical retrieval |
| Reranking | Cohere Rerank API | Result quality improvement |
| Agent Framework | LangGraph | Stateful multi-step reasoning |
| LLM | GPT-4o | Report synthesis |
| Observability | LangSmith | Agent trace monitoring |

**Chunking strategy:** Semantic chunking over financial documents — not naive fixed-size chunking. Preserves financial context across paragraph boundaries.

**Retrieval strategy:** Hybrid dense + sparse retrieval with Cohere reranking. Pure vector search misses exact ticker/term matches. Pure BM25 misses semantic similarity. Hybrid + rerank gets both.

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** — Async Python web framework
- **SQLAlchemy (async)** + **asyncpg** — Async ORM + PostgreSQL driver
- **Alembic** — Database migrations
- **pydantic-settings** — Type-safe config management
- **structlog** — Structured JSON logging
- **APScheduler** — Periodic filing ingestion jobs
- **slowapi** — API rate limiting
- **python-jose** + **passlib** — JWT auth + password hashing

### Database & Infrastructure
- **PostgreSQL 16** + **pgvector** — Relational + vector storage in one place
- **Redis 7** — APScheduler job state + caching
- **Docker Compose** — Local development orchestration

### Frontend
- **React** + **TypeScript**
- **TanStack Query** — Server state management
- **Tailwind CSS** — Utility-first styling
- **SSE** — Real-time agent response streaming

### Data Sources
- **SEC EDGAR API** — 10-K / 10-Q filings + earnings transcripts
- **yfinance** — Price data + fundamentals
- **NewsAPI** — Financial news

### Testing & CI/CD
- **pytest** + **pytest-asyncio** — Backend unit + integration tests
- **Playwright** — End-to-end testing
- **GitHub Actions** — CI/CD pipeline
- **Railway** — Cloud deployment

---

## 🚀 Getting Started

### Prerequisites
- Docker Desktop
- Python 3.12+
- Node.js 20+

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/stock-research-assistant.git
cd stock-research-assistant
```

### 2. Configure environment
```bash
cp backend/.env.example backend/.env
```

Fill in the required values in `backend/.env`:

| Variable | Where to get it |
|---|---|
| `SECRET_KEY` | Run `openssl rand -hex 32` |
| `OPENAI_API_KEY` | platform.openai.com |
| `LANGCHAIN_API_KEY` | smith.langchain.com |
| `COHERE_API_KEY` | dashboard.cohere.com |
| `NEWS_API_KEY` | newsapi.org |

### 3. Start infrastructure
```bash
docker compose up --build
```

### 4. Run database migrations
```bash
docker compose exec backend alembic upgrade head
```

### 5. Verify the app is running
```bash
curl http://localhost:8000/api/v1/health
```

Expected:
```json
{
  "status": "ok",
  "database": "healthy"
}
```

---

## 🗂️ Project Structure

```
stock-research-assistant/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       └── routes/          # Route handlers
│   │   ├── core/
│   │   │   ├── config.py            # pydantic-settings config
│   │   │   └── logging.py           # structlog setup
│   │   ├── db/
│   │   │   ├── base.py              # SQLAlchemy declarative base
│   │   │   ├── session.py           # Async engine + session
│   │   │   └── migrations/          # Alembic migrations
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   └── main.py                  # FastAPI app entry point
│   ├── tests/                       # pytest test suite
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                        # React + TypeScript app
├── docker-compose.yml
└── README.md
```

---

## 🧪 Testing

### Backend unit + integration tests
```bash
docker compose exec backend pytest tests/ -v
```

### End-to-end tests
```bash
cd frontend
npx playwright test
```

### Run full test suite (CI)
```bash
docker compose exec backend pytest tests/ -v
npx playwright test --reporter=html
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/auth/register` | Register user |
| `POST` | `/api/v1/auth/login` | Login + get JWT |
| `GET` | `/api/v1/tickers/search` | Search tickers |
| `POST` | `/api/v1/reports/generate` | Trigger report generation |
| `GET` | `/api/v1/reports/{id}` | Fetch generated report |
| `GET` | `/api/v1/reports/{id}/stream` | Stream agent response (SSE) |
| `GET` | `/api/v1/watchlist` | Get user watchlist |
| `POST` | `/api/v1/watchlist` | Add ticker to watchlist |
| `DELETE` | `/api/v1/watchlist/{ticker}` | Remove from watchlist |

---

## 🔭 Build Phases

- [x] **Phase 1** — Project Foundation
- [ ] **Phase 2** — Data Ingestion Pipeline (SEC EDGAR, yfinance, NewsAPI, APScheduler)
- [ ] **Phase 3** — RAG Pipeline (Chunking, Embeddings, Hybrid Retrieval, Reranking)
- [ ] **Phase 4** — Agent Layer (LangGraph, Tools, LangSmith)
- [ ] **Phase 5** — FastAPI Backend (Auth, SSE, Rate Limiting)
- [ ] **Phase 6** — Testing (pytest, Playwright, GitHub Actions)
- [ ] **Phase 7** — Frontend (React, TanStack Query, Tailwind)

---

## 🔐 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `APP_ENV` | No | `development` or `production` |
| `SECRET_KEY` | Yes | JWT signing key |
| `POSTGRES_USER` | Yes | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `POSTGRES_DB` | Yes | PostgreSQL database name |
| `POSTGRES_HOST` | No | Defaults to `postgres` (Docker service name) |
| `POSTGRES_PORT` | No | Defaults to `5432` |
| `REDIS_HOST` | No | Defaults to `redis` (Docker service name) |
| `REDIS_PORT` | No | Defaults to `6379` |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `LANGCHAIN_TRACING_V2` | No | Defaults to `true` |
| `LANGCHAIN_API_KEY` | Yes | LangSmith API key |
| `LANGCHAIN_PROJECT` | No | Defaults to `stock-research-assistant` |
| `COHERE_API_KEY` | Yes | Cohere Rerank API key |
| `NEWS_API_KEY` | Yes | NewsAPI key |

---


<p align="center">Built with precision. Grounded in real data. Designed for production.</p>
