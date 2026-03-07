from datetime import datetime, date as date_type
from sqlalchemy import String, DateTime, Date, Text, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (
        UniqueConstraint("ticker_id", "accession_number", name="uq_filings_ticker_accession"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filing_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    period_of_report: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_chunked: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ticker: Mapped["Ticker"] = relationship(back_populates="filings")
    chunks: Mapped[list["FilingChunk"]] = relationship(back_populates="filing", cascade="all, delete-orphan")