from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScreenerFetchJob(Base):
    """One request to pull & analyse a sector from screener.in."""

    __tablename__ = "screener_fetch_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sector_key = Column(String(100), nullable=False, index=True)
    sector_label = Column(String(150), nullable=False)
    status = Column(String(20), nullable=False, default="running")  # running | success | failed
    error_message = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    stocks = relationship(
        "ScreenerStockMetric", back_populates="job", cascade="all, delete-orphan"
    )


class ScreenerStockMetric(Base):
    """One analysed stock row belonging to a ScreenerFetchJob."""

    __tablename__ = "screener_stock_metrics"

    id = Column(Integer, primary_key=True, index=True)
    fetch_job_id = Column(Integer, ForeignKey("screener_fetch_jobs.id"), nullable=False, index=True)
    row_order = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    metrics = Column(JSON, nullable=False)
    highlights = Column(JSON, nullable=False)

    job = relationship("ScreenerFetchJob", back_populates="stocks")


class PortfolioUpload(Base):
    """One broker-app screenshot a user uploaded to have its holdings extracted.

    A user's portfolio is usually built from *several* of these - one broker's
    holdings screen often needs more than one screenshot to show every
    position, and a user may hold stocks across more than one broker. Each
    upload's extracted rows are merged into the user's single consolidated
    PortfolioHolding list (see services/portfolio/merge.py); this table exists
    so the user can see upload history and "last uploaded on" even though the
    holdings themselves live independently of any one upload.
    """

    __tablename__ = "portfolio_uploads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    image_path = Column(String(500), nullable=False)
    broker = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="running")  # running | success | failed
    error_message = Column(Text, nullable=True)
    holdings_found = Column(Integer, nullable=False, default=0)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioHolding(Base):
    """One consolidated holding in a user's portfolio.

    Rows are keyed per-user (not per-upload): re-uploading the same broker's
    screen updates matching rows in place, a second screenshot of the same
    broker's partial list adds the rows it was missing, and a screenshot from
    a different broker adds its holdings alongside the rest. Users can also
    add/edit/delete rows by hand to fix OCR mistakes or make the totals match
    their broker app exactly.
    """

    __tablename__ = "portfolio_holdings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_upload_id = Column(Integer, ForeignKey("portfolio_uploads.id"), nullable=True)
    broker = Column(String(100), nullable=True)
    raw_name = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=True)
    avg_price = Column(Float, nullable=True)
    ltp = Column(Float, nullable=True)
    invested_value = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    resolved_name = Column(String(255), nullable=True)
    resolved_url = Column(String(255), nullable=True)
    price_synced_at = Column(DateTime(timezone=True), nullable=True)
    price_is_approximate = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CompanySector(Base):
    """A company's screener.in sector/industry, shared across all users.

    Looked up once per company (it effectively never changes) so a portfolio
    breakdown by sector doesn't re-fetch every company page on each view.
    """

    __tablename__ = "company_sectors"

    id = Column(Integer, primary_key=True, index=True)
    company_url = Column(String(255), unique=True, index=True, nullable=False)
    sector = Column(String(150), nullable=False)
    industry = Column(String(150), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class CompanyAnalysisCache(Base):
    """Cached per-company analysis (quarterly/yearly P&L + shareholding).

    Shared across all users (unlike ScreenerFetchJob) since it's just public
    financial data keyed by the company's screener.in URL - there's no reason
    for two users looking at the same company to each spend a screener.in
    request.
    """

    __tablename__ = "company_analysis_cache"

    id = Column(Integer, primary_key=True, index=True)
    company_url = Column(String(255), unique=True, index=True, nullable=False)
    company_name = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
