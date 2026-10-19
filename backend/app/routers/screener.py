import io
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.exceptions import DataShapeMismatchError, ScreenerError, ScreenerSessionExpiredError, SectorNotFoundError
from app.services.screener import analyzer, excel_export, scoring, sectors
from app.services.screener.fetcher import get_fetcher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.get("/sectors", response_model=list[schemas.SectorOut])
def list_sectors(current_user: models.User = Depends(get_current_user)):
    return sectors.list_sectors()


@router.post("/fetch", response_model=schemas.FetchJobDetailOut, status_code=status.HTTP_201_CREATED)
def fetch_sector(
    payload: schemas.FetchRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        sector_url = sectors.get_sector_url(payload.sector_key)
        sector_label = sectors.get_sector_label(payload.sector_key)
    except SectorNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not payload.force_refresh:
        cached_job = _find_fresh_cached_job(db, current_user, payload.sector_key)
        if cached_job is not None:
            logger.info(
                "Serving sector '%s' for user %s from cached job %s (fetched %s)",
                payload.sector_key, current_user.id, cached_job.id, cached_job.completed_at,
            )
            return _to_detail(cached_job, from_cache=True)

    job = models.ScreenerFetchJob(
        user_id=current_user.id,
        sector_key=payload.sector_key,
        sector_label=sector_label,
        status="running",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info("User %s started fetch job %s for sector '%s'", current_user.id, job.id, payload.sector_key)

    try:
        fetcher = get_fetcher()
        raw_table = fetcher.fetch_sector(sector_url)
        clean_table = analyzer.clean_and_enrich(raw_table)
        # Round-tripping through JSON converts numpy scalars to plain Python
        # int/float/str so the values are safe to store in a JSON column and
        # return straight from the API.
        records = json.loads(clean_table.to_json(orient="records"))

        for row_order, record in enumerate(records):
            name = record.pop("Name")
            db.add(
                models.ScreenerStockMetric(
                    fetch_job_id=job.id,
                    row_order=row_order,
                    name=name,
                    metrics=record,
                    highlights=scoring.score_row(record),
                )
            )

        job.status = "success"
        job.row_count = len(records)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    except ScreenerSessionExpiredError as exc:
        _mark_failed(db, job, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (DataShapeMismatchError, ScreenerError) as exc:
        _mark_failed(db, job, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort guard so a job is never left "running"
        logger.exception("Unexpected error while fetching sector '%s'", payload.sector_key)
        _mark_failed(db, job, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while analysing sector data",
        ) from exc

    db.refresh(job)
    return _to_detail(job)


def _find_fresh_cached_job(
    db: Session, current_user: models.User, sector_key: str
) -> models.ScreenerFetchJob | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.SCREENER_CACHE_TTL_HOURS)
    return (
        db.query(models.ScreenerFetchJob)
        .filter(
            models.ScreenerFetchJob.user_id == current_user.id,
            models.ScreenerFetchJob.sector_key == sector_key,
            models.ScreenerFetchJob.status == "success",
            models.ScreenerFetchJob.completed_at >= cutoff,
        )
        .order_by(models.ScreenerFetchJob.completed_at.desc())
        .first()
    )


@router.get("/jobs", response_model=list[schemas.FetchJobSummaryOut])
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.ScreenerFetchJob)
        .filter(models.ScreenerFetchJob.user_id == current_user.id)
        .order_by(models.ScreenerFetchJob.requested_at.desc())
        .offset(offset)
        .limit(min(limit, 100))
        .all()
    )


@router.get("/jobs/{job_id}", response_model=schemas.FetchJobDetailOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    job = _get_owned_job(db, job_id, current_user)
    return _to_detail(job)


@router.get("/jobs/{job_id}/export")
def export_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    job = _get_owned_job(db, job_id, current_user)
    detail = _to_detail(job)
    workbook_bytes = excel_export.build_workbook(job.sector_label, detail.rows)
    excel_export.archive_to_disk(workbook_bytes, job.sector_key, job.completed_at or job.requested_at)
    filename = f"{job.sector_key}_{job.requested_at:%Y%m%d}.xlsx"
    return StreamingResponse(
        io.BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _mark_failed(db: Session, job: models.ScreenerFetchJob, exc: Exception) -> None:
    db.rollback()
    job.status = "failed"
    job.error_message = str(exc)
    job.completed_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    logger.warning("Fetch job %s failed: %s", job.id, exc)


def _get_owned_job(db: Session, job_id: int, current_user: models.User) -> models.ScreenerFetchJob:
    job = db.query(models.ScreenerFetchJob).filter(models.ScreenerFetchJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fetch job not found")
    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this fetch job")
    return job


def _to_detail(job: models.ScreenerFetchJob, from_cache: bool = False) -> schemas.FetchJobDetailOut:
    rows = sorted(job.stocks, key=lambda stock: stock.row_order)
    return schemas.FetchJobDetailOut(
        id=job.id,
        sector_key=job.sector_key,
        sector_label=job.sector_label,
        status=job.status,
        error_message=job.error_message,
        row_count=job.row_count,
        requested_at=job.requested_at,
        completed_at=job.completed_at,
        from_cache=from_cache,
        rows=[
            schemas.StockRowOut(name=stock.name, metrics=stock.metrics, highlights=stock.highlights)
            for stock in rows
        ],
    )
