from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, func
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
