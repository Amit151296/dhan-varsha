from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SectorOut(BaseModel):
    key: str
    label: str


class FetchRequest(BaseModel):
    sector_key: str
    force_refresh: bool = False


class Highlight(BaseModel):
    zone: str
    background: str
    color: str


class StockRowOut(BaseModel):
    name: str
    metrics: dict[str, Any]
    highlights: dict[str, Highlight]


class FetchJobSummaryOut(BaseModel):
    id: int
    sector_key: str
    sector_label: str
    status: str
    error_message: str | None = None
    row_count: int
    requested_at: datetime
    completed_at: datetime | None = None
    from_cache: bool = False

    class Config:
        from_attributes = True


class FetchJobDetailOut(FetchJobSummaryOut):
    rows: list[StockRowOut]


class CompanySearchResult(BaseModel):
    name: str
    url: str


class ResolveCompanyRequest(BaseModel):
    name: str


class CompanyAnalyseRequest(BaseModel):
    url: str
    company_name: str | None = None
    force_refresh: bool = False


class PortfolioHoldingOut(BaseModel):
    id: int
    broker: str | None = None
    raw_name: str
    quantity: float | None = None
    avg_price: float | None = None
    ltp: float | None = None
    invested_value: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    resolved_name: str | None = None
    resolved_url: str | None = None
    price_synced_at: datetime | None = None
    price_is_approximate: bool = False
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioHoldingCreate(BaseModel):
    company_name: str
    quantity: float | None = None
    avg_price: float | None = None
    ltp: float | None = None
    invested_value: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    resolved_name: str | None = None
    resolved_url: str | None = None


class PortfolioHoldingUpdate(BaseModel):
    raw_name: str | None = None
    broker: str | None = None
    quantity: float | None = None
    avg_price: float | None = None
    ltp: float | None = None
    invested_value: float | None = None
    current_value: float | None = None
    pnl: float | None = None


class PortfolioSummaryOut(BaseModel):
    total_invested: float
    total_current_value: float
    total_pnl: float
    holding_count: int


class PortfolioOut(BaseModel):
    holdings: list[PortfolioHoldingOut]
    summary: PortfolioSummaryOut
    last_upload_at: datetime | None = None
    last_synced_at: datetime | None = None
    unsynced: list[str] = []
    skipped: list[str] = []
    upload_broker: str | None = None
    upload_holdings: int = 0


class BreakdownRowOut(BaseModel):
    label: str
    company_count: int
    invested: float
    current_value: float
    pnl: float
    share_of_invested: float
    companies: list[str]


class PortfolioAnalysisOut(BaseModel):
    total_invested: float
    company_count: int
    by_broker: list[BreakdownRowOut]
    by_sector: list[BreakdownRowOut]
    by_industry: list[BreakdownRowOut] = []
    by_concentration: list[BreakdownRowOut] = []


class PortfolioUploadSummaryOut(BaseModel):
    id: int
    broker: str | None = None
    status: str
    error_message: str | None = None
    holdings_found: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class CompanyAnalysisOut(BaseModel):
    company_name: str
    url: str
    fetched_at: datetime
    from_cache: bool = False
    standalone: dict[str, Any]
    consolidated: dict[str, Any] | None = None
    shareholding: dict[str, Any]


class InsightItemOut(BaseModel):
    title: str
    detail: str = ""
    companies: list[str] = []


class PortfolioInsightsOut(BaseModel):
    summary: str = ""
    strengths: list[InsightItemOut] = []
    risks: list[InsightItemOut] = []
    watchlist: list[str] = []
    standouts: list[str] = []
    data_gaps: list[str] = []
    source: str  # "ai" | "rules"
    ai_error: str | None = None
    cached: bool = False
    generated_at: datetime | None = None


class IndexRowOut(BaseModel):
    name: str
    slug: str | None = None
    ltp: float | None = None
    day_change_pct: float | None = None
    prev_close: float | None = None
    high_52w: float | None = None
    up_from_low_pct: float | None = None
    low_52w: float | None = None
    return_1w: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None
    return_3y: float | None = None
    return_5y: float | None = None


class IndexPerformanceOut(BaseModel):
    rows: list[IndexRowOut]
    fetched_at: datetime
    expires_at: datetime
    cached: bool
    stale: bool = False


class IndexMemberOut(BaseModel):
    name: str
    symbol: str | None = None
    sector: str | None = None
    ltp: float | None = None
    day_change_pct: float | None = None
    market_cap_cr: float | None = None
    pe: float | None = None
    low_52w: float | None = None
    high_52w: float | None = None
    up_from_low_pct: float | None = None


class IndexMembersOut(BaseModel):
    index_name: str
    slug: str
    rows: list[IndexMemberOut]
    fetched_at: datetime
    expires_at: datetime
    cached: bool
    stale: bool = False
