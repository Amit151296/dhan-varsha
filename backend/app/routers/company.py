import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.exceptions import DataShapeMismatchError, ScreenerError, ScreenerSessionExpiredError
from app.services.company import search as company_search
from app.services.company.analyzer import analyse_company, canonical_company_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/search", response_model=list[schemas.CompanySearchResult])
def search(q: str = "", current_user: models.User = Depends(get_current_user)):
    try:
        return company_search.search_companies(q)
    except ScreenerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/resolve", response_model=schemas.CompanySearchResult)
def resolve(
    payload: schemas.ResolveCompanyRequest,
    current_user: models.User = Depends(get_current_user),
):
    try:
        match = company_search.resolve_company_by_name(payload.name)
    except ScreenerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No screener.in listing found matching '{payload.name}'",
        )
    return match


@router.post("/analyse", response_model=schemas.CompanyAnalysisOut)
def analyse(
    payload: schemas.CompanyAnalyseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cache_key = canonical_company_key(payload.url)

    if not payload.force_refresh:
        cached = _find_fresh_cache(db, cache_key)
        if cached is not None:
            logger.info("Serving company '%s' from cache (fetched %s)", cache_key, cached.fetched_at)
            return schemas.CompanyAnalysisOut(
                company_name=cached.company_name,
                url=cached.company_url,
                fetched_at=cached.fetched_at,
                from_cache=True,
                **cached.payload,
            )

    try:
        payload_dict = analyse_company(payload.url)
    except ScreenerSessionExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (DataShapeMismatchError, ScreenerError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        logger.exception("Unexpected error analysing company '%s'", payload.url)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while analysing company data",
        ) from exc

    company_name = payload.company_name or _ticker_from_url(payload.url)
    fetched_at = datetime.now(timezone.utc)

    cache_row = db.query(models.CompanyAnalysisCache).filter(
        models.CompanyAnalysisCache.company_url == cache_key
    ).first()
    if cache_row is None:
        cache_row = models.CompanyAnalysisCache(company_url=cache_key)
        db.add(cache_row)
    cache_row.company_name = company_name
    cache_row.payload = payload_dict
    cache_row.fetched_at = fetched_at
    db.commit()

    return schemas.CompanyAnalysisOut(
        company_name=company_name,
        url=cache_key,
        fetched_at=fetched_at,
        from_cache=False,
        **payload_dict,
    )


def _find_fresh_cache(db: Session, company_url: str) -> models.CompanyAnalysisCache | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.SCREENER_CACHE_TTL_HOURS)
    return (
        db.query(models.CompanyAnalysisCache)
        .filter(
            models.CompanyAnalysisCache.company_url == company_url,
            models.CompanyAnalysisCache.fetched_at >= cutoff,
        )
        .first()
    )


def _ticker_from_url(url: str) -> str:
    parts = [p for p in url.split("/") if p]
    return parts[1] if len(parts) > 1 else url
