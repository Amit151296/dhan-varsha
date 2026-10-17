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


class Highlight(BaseModel):
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

    class Config:
        from_attributes = True


class FetchJobDetailOut(FetchJobSummaryOut):
    rows: list[StockRowOut]
