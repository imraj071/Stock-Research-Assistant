import re
import httpx
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ticker import Ticker
from app.models.filing import Filing
from app.core.logging import logger

EDGAR_BASE_URL = "https://data.sec.gov"
EDGAR_SEARCH_URL = "https://efts.sec.gov"
HEADERS = {
    "User-Agent": "StockResearchAssistant contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


async def get_or_create_ticker(
    db: AsyncSession,
    symbol: str,
    company_name: str,
    sector: str | None = None,
    industry: str | None = None,
    market_cap: float | None = None,
) -> Ticker:
    result = await db.execute(
        select(Ticker).where(Ticker.symbol == symbol.upper())
    )
    ticker = result.scalar_one_or_none()

    if ticker is None:
        ticker = Ticker(
            symbol=symbol.upper(),
            company_name=company_name,
            sector=sector,
            industry=industry,
            market_cap=market_cap,
        )
        db.add(ticker)
        await db.commit()
        await db.refresh(ticker)
        logger.info("ticker_created", symbol=symbol)
    else:
        logger.info("ticker_exists", symbol=symbol)

    return ticker


async def fetch_cik(symbol: str) -> str | None:
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        try:
            tickers_url = "https://www.sec.gov/files/company_tickers.json"
            response = await client.get(tickers_url)
            response.raise_for_status()
            data = response.json()

            for entry in data.values():
                if entry.get("ticker", "").upper() == symbol.upper():
                    cik = str(entry["cik_str"]).zfill(10)
                    logger.info("cik_found", symbol=symbol, cik=cik)
                    return cik

            logger.warning("cik_not_found", symbol=symbol)
            return None

        except Exception as e:
            logger.error("cik_fetch_failed", symbol=symbol, error=str(e))
            return None


async def fetch_filings_for_cik(
    cik: str,
    doc_types: list[str] = ["10-K", "10-Q"],
) -> list[dict]:
    url = f"{EDGAR_BASE_URL}/submissions/CIK{cik}.json"

    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            filings = data.get("filings", {}).get("recent", {})
            forms = filings.get("form", [])
            accession_numbers = filings.get("accessionNumber", [])
            filing_dates = filings.get("filingDate", [])
            report_dates = filings.get("reportDate", [])
            primary_documents = filings.get("primaryDocument", [])

            results = []
            for i, form in enumerate(forms):
                if form in doc_types:
                    results.append({
                        "doc_type": form,
                        "accession_number": accession_numbers[i],
                        "filing_date": filing_dates[i],
                        "period_of_report": report_dates[i] if report_dates[i] else None,
                        "primary_document": primary_documents[i],
                        "cik": cik,
                    })

            logger.info("filings_fetched", cik=cik, count=len(results))
            return results

        except Exception as e:
            logger.error("filings_fetch_failed", cik=cik, error=str(e))
            return []


async def fetch_filing_text(
    cik: str,
    accession_number: str,
    primary_document: str,
) -> str | None:
    clean_accession = accession_number.replace("-", "")
    url = (
        f"{EDGAR_BASE_URL}/Archives/edgar/full-index/"
        f"Archives/edgar/data/{int(cik)}/"
        f"{clean_accession}/{primary_document}"
    )

    async with httpx.AsyncClient(headers=HEADERS, timeout=60.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text
            clean_text = re.sub(r'<[^>]+>', ' ', text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            logger.info(
                "filing_text_fetched",
                accession_number=accession_number,
                chars=len(clean_text)
            )
            return clean_text

        except Exception as e:
            logger.error(
                "filing_text_fetch_failed",
                accession_number=accession_number,
                error=str(e)
            )
            return None


async def ingest_filings_for_ticker(
    db: AsyncSession,
    symbol: str,
    doc_types: list[str] = ["10-K", "10-Q"],
    max_filings: int = 5,
) -> dict:
    logger.info("ingestion_started", symbol=symbol)

    cik = await fetch_cik(symbol)
    if not cik:
        return {"success": False, "error": f"CIK not found for {symbol}"}

    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        try:
            submissions_url = f"{EDGAR_BASE_URL}/submissions/CIK{cik}.json"
            response = await client.get(submissions_url)
            response.raise_for_status()
            data = response.json()
            company_name = data.get("name", symbol)
        except Exception as e:
            logger.error("company_name_fetch_failed", symbol=symbol, error=str(e))
            company_name = symbol

    ticker = await get_or_create_ticker(db, symbol, company_name)

    filing_records = await fetch_filings_for_cik(cik, doc_types)
    filing_records = filing_records[:max_filings]

    ingested = 0
    skipped = 0

    for record in filing_records:
        result = await db.execute(
            select(Filing).where(
                Filing.ticker_id == ticker.id,
                Filing.accession_number == record["accession_number"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            skipped += 1
            continue

        raw_text = await fetch_filing_text(
            cik=cik,
            accession_number=record["accession_number"],
            primary_document=record["primary_document"],
        )

        filing_date = date.fromisoformat(record["filing_date"])
        period_of_report = (
            date.fromisoformat(record["period_of_report"])
            if record["period_of_report"]
            else None
        )

        filing = Filing(
            ticker_id=ticker.id,
            accession_number=record["accession_number"],
            doc_type=record["doc_type"],
            filing_date=filing_date,
            period_of_report=period_of_report,
            raw_text=raw_text,
            source_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{record['accession_number'].replace('-', '')}/{record['primary_document']}",
            is_chunked=False,
        )
        db.add(filing)
        ingested += 1

    await db.commit()

    logger.info(
        "ingestion_complete",
        symbol=symbol,
        ingested=ingested,
        skipped=skipped,
    )

    return {
        "success": True,
        "symbol": symbol,
        "ingested": ingested,
        "skipped": skipped,
    }