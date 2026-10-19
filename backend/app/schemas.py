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


class CompanyAnalysisOut(BaseModel):
    company_name: str
    url: str
    fetched_at: datetime
    from_cache: bool = False
    standalone: dict[str, Any]
    consolidated: dict[str, Any] | None = None
    shareholding: dict[str, Any]
