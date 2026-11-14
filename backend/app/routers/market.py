import io
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.services.market import index_performance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/indices", response_model=schemas.IndexPerformanceOut)
def nse_index_performance(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """NSE index performance. The same for everyone and fetched at most once a day (cached until midnight IST)."""
    try:
        return index_performance.get_index_performance(db)
    except index_performance.IndexDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/indices/{slug}/companies", response_model=schemas.IndexMembersOut)
def nse_index_companies(
    slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Companies in one tracked index, largest first. Fetched when first opened and shared until midnight IST."""
    try:
        return index_performance.get_index_members(db, slug)
    except index_performance.IndexNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown index.") from exc
    except index_performance.IndexDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/indices/export")
def export_nse_index_performance(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The same table as an Excel file (plain numbers, so it can be sorted and filtered there)."""
    try:
        data = index_performance.get_index_performance(db)
    except index_performance.IndexDataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    filename = f"NSE_index_performance_{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        io.BytesIO(index_performance.build_workbook(data["rows"])),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
