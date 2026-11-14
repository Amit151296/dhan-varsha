import io
import json
import logging
import os
import re
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.exceptions import PortfolioExtractionError, ScreenerError
from app.routers import screener as screener_router
from app.services.company.analyzer import canonical_company_key
from app.services.portfolio import metrics as portfolio_metrics
from app.services.portfolio import prices, sectors
from app.services.screener import analyzer as screener_analyzer
from app.services.screener import scoring
from app.services.portfolio.analysis import NO_BROKER_LABEL, analyse_portfolio, holding_amounts
from app.services.html_export import build_analysis_html
from app.services.portfolio.analysis_export import build_analysis_workbook
from app.services.portfolio.concentration import concentration_breakdown
from app.services.portfolio import insights as portfolio_insights
from app.services.portfolio.extractor import extract_holdings_from_image
from app.services.portfolio.matcher import match_holdings, resolve_company
from app.services.portfolio.merge import merge_holdings_into_portfolio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
PORTFOLIO_METRICS_KEY = "__portfolio__"


@router.get("", response_model=schemas.PortfolioOut)
def get_portfolio(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return _build_portfolio_out(db, current_user.id)


def _user_holdings(db: Session, user: models.User, broker: str | None = None) -> list:
    """The user's holdings, optionally only those at one broker (NO_BROKER_LABEL = no broker recorded)."""
    holdings = db.query(models.PortfolioHolding).filter(models.PortfolioHolding.user_id == user.id).all()
    broker = (broker or "").strip()
    if not broker:
        return holdings
    if broker == NO_BROKER_LABEL:
        return [h for h in holdings if not h.broker]
    return [h for h in holdings if (h.broker or "").casefold() == broker.casefold()]


@router.get("/analysis", response_model=schemas.PortfolioAnalysisOut)
def get_portfolio_analysis(
    broker: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _analysis_for(db, current_user, broker)[1]


def _portfolio_title(user: models.User, broker: str | None = None) -> str:
    name = (user.full_name or "").strip()
    base = f"{name}'s Portfolio" if name else "My Portfolio"
    return f"{base} ({broker})" if broker else base


def _analysis_for(db: Session, user: models.User, broker: str | None) -> tuple[list, dict]:
    holdings = _user_holdings(db, user, broker)
    company_sectors = sectors.get_sectors(db, [h.resolved_url for h in holdings if h.resolved_url])
    result = analyse_portfolio(holdings, company_sectors)
    result["by_concentration"] = concentration_breakdown(holdings)
    return holdings, result


@router.post("/metrics/{job_id}/insights", response_model=schemas.PortfolioInsightsOut)
def portfolio_insights_for_job(
    job_id: int,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Strengths and risks of the portfolio, read off the colour-coded metrics table of this job.

    Written by OpenAI from the sheet (one call per distinct sheet, then saved). If OpenAI can't be
    reached, the rule-based findings are returned instead, with `ai_error` saying why.
    """
    job = screener_router._get_owned_job(db, job_id, current_user)
    if not job.sector_key.startswith(PORTFOLIO_METRICS_KEY) or job.status != "success":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insights are only available for a fetched portfolio table.")
    rows = [SimpleNamespace(name=s.name, metrics=s.metrics, highlights=s.highlights) for s in sorted(job.stocks, key=lambda s: s.row_order)]
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The metrics table is empty.")

    digest = portfolio_insights.input_hash(rows)
    saved = (
        db.query(models.PortfolioInsight)
        .filter(models.PortfolioInsight.user_id == current_user.id, models.PortfolioInsight.input_hash == digest)
        .first()
    )
    if saved is not None and not refresh:
        return schemas.PortfolioInsightsOut(**saved.result, source="ai", cached=True, generated_at=saved.created_at)

    try:
        result = portfolio_insights.generate_insights(rows)
    except RuntimeError as exc:
        return schemas.PortfolioInsightsOut(**portfolio_insights.rules_only_insights(rows), source="rules", ai_error=str(exc))

    now = datetime.now(timezone.utc)
    if saved is None:
        db.add(models.PortfolioInsight(user_id=current_user.id, input_hash=digest, result=result, created_at=now))
    else:
        saved.result, saved.created_at = result, now
    db.commit()
    return schemas.PortfolioInsightsOut(**result, source="ai", generated_at=now)


def _saved_metric_rows(db: Session, holdings: list):
    """Metric rows for the holdings from the shared saved data only (no screener.in call).

    Returns (rows, oldest data date, names of holdings that have no saved data yet).
    """
    tickers = portfolio_metrics.tickers_for_holdings(holdings)
    if not tickers:
        return [], None, []
    raw = portfolio_metrics.fetch_portfolio_metrics(db, tickers, cache_only=True)
    if raw.empty:
        return [], None, sorted(h.raw_name for h in holdings)
    as_of = raw.attrs["as_of"]
    clean = screener_analyzer.clean_and_enrich(raw)
    rows = []
    for record in json.loads(clean.to_json(orient="records")):
        name = record.pop("Name")
        highlights = {col: SimpleNamespace(**value) for col, value in scoring.score_row(record).items()}
        rows.append(SimpleNamespace(name=name, metrics=record, highlights=highlights))
    shown = {row.name.casefold() for row in rows}
    missing = sorted(
        {h.raw_name for h in holdings if (h.resolved_name or h.raw_name).casefold() not in shown and h.raw_name.casefold() not in shown}
    )
    return rows, as_of, missing


def _saved_insights(db: Session, user: models.User, broker: str | None):
    """The strength/risk analysis already generated for this user's metrics table, or None. Never calls OpenAI."""
    key = f"{PORTFOLIO_METRICS_KEY}:{broker.casefold()[:80]}" if broker else PORTFOLIO_METRICS_KEY
    job = (
        db.query(models.ScreenerFetchJob)
        .filter(
            models.ScreenerFetchJob.user_id == user.id,
            models.ScreenerFetchJob.sector_key == key,
            models.ScreenerFetchJob.status == "success",
        )
        .order_by(models.ScreenerFetchJob.id.desc())
        .first()
    )
    if job is None or not job.stocks:
        return None
    rows = [SimpleNamespace(name=s.name, metrics=s.metrics, highlights=s.highlights) for s in sorted(job.stocks, key=lambda s: s.row_order)]
    saved = (
        db.query(models.PortfolioInsight)
        .filter(models.PortfolioInsight.user_id == user.id, models.PortfolioInsight.input_hash == portfolio_insights.input_hash(rows))
        .first()
    )
    return saved.result if saved else None


@router.get("/report")
def export_portfolio_report(
    broker: str | None = None,
    format: str = "html",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """One file with everything on the portfolio page: holdings, analysis tables and company metrics.

    Metrics come from the shared saved data, so downloading never calls screener.in.
    """
    if format not in ("xlsx", "html"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be 'xlsx' or 'html'")
    broker = (broker or "").strip() or None
    holdings, analysis = _analysis_for(db, current_user, broker)
    if not holdings:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No holdings to export.")
    metric_rows, as_of, missing = _saved_metric_rows(db, holdings)
    insights = _saved_insights(db, current_user, broker)
    title = _portfolio_title(current_user, broker)
    if format == "html":
        data = build_analysis_html(title, holdings, analysis, broker, metric_rows, as_of, missing, insights)
        media_type = "text/html; charset=utf-8"
    else:
        data = build_analysis_workbook(holdings, analysis, broker, owner=current_user.full_name, metric_rows=metric_rows, insights=insights)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    slug = re.sub(r"\W+", "_", title).strip("_")
    filename = f"{slug}_{datetime.now():%Y%m%d}.{format}"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _run_metrics_job(db, user, key, label, build_clean_table):
    """Build the table, score it and save it as this user's job (replacing their previous one for `key`).

    `build_clean_table` returns (table, as_of, from_cache): `as_of` is how old the data is and
    `from_cache` says screener.in wasn't called. The job itself is cheap to rebuild because the
    expensive part - the shared per-company snapshots - is cached across all users, and rebuilding
    means the table always matches the holdings as they are now.
    """
    for old in db.query(models.ScreenerFetchJob).filter(
        models.ScreenerFetchJob.user_id == user.id, models.ScreenerFetchJob.sector_key == key
    ):
        db.delete(old)
    job = models.ScreenerFetchJob(user_id=user.id, sector_key=key, sector_label=label, status="running")
    db.add(job)
    db.commit()
    db.refresh(job)

    from_cache = False
    try:
        clean_table, as_of, from_cache = build_clean_table()
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
        job.completed_at = as_of  # the banner says "data from ...", so this is when the numbers were fetched
        db.commit()
    except ScreenerError as exc:
        screener_router._mark_failed(db, job, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort guard so a job is never left "running"
        logger.exception("Unexpected error while building portfolio metrics")
        screener_router._mark_failed(db, job, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while building portfolio metrics",
        ) from exc

    db.refresh(job)
    return screener_router._to_detail(job, from_cache=from_cache)


def _matched_tickers(db: Session, user: models.User, broker: str | None = None):
    holdings = _user_holdings(db, user, broker)
    tickers = portfolio_metrics.tickers_for_holdings(holdings)
    if not tickers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No holdings with a matched company yet. Add or sync holdings first."
            if not broker
            else f"No holdings with a matched company at '{broker}'.",
        )
    return holdings, tickers


@router.post("/metrics", response_model=schemas.FetchJobDetailOut, status_code=status.HTTP_201_CREATED)
def fetch_portfolio_metrics(
    force_refresh: bool = False,
    broker: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    broker = (broker or "").strip() or None
    _, tickers = _matched_tickers(db, current_user, broker)
    # Each broker gets its own cached job, so switching filters never shows another broker's table.
    key = f"{PORTFOLIO_METRICS_KEY}:{broker.casefold()[:80]}" if broker else PORTFOLIO_METRICS_KEY

    def build():
        raw = portfolio_metrics.fetch_portfolio_metrics(db, tickers, force_refresh=force_refresh)
        return screener_analyzer.clean_and_enrich(raw), raw.attrs["as_of"], not raw.attrs["fetched"]

    return _run_metrics_job(db, current_user, key, _portfolio_title(current_user, broker), build)


@router.post("/upload", response_model=schemas.PortfolioOut, status_code=status.HTTP_201_CREATED)
async def upload_portfolio_screenshot(
    file: UploadFile,
    broker: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a PNG, JPEG, or WEBP screenshot of your holdings screen.",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Screenshot is too large (max 10 MB).")

    broker = (broker or "").strip() or None
    image_path = _save_upload(current_user.id, file.content_type, image_bytes)

    upload = models.PortfolioUpload(user_id=current_user.id, image_path=image_path, broker=broker, status="running")
    db.add(upload)
    db.commit()
    db.refresh(upload)

    try:
        detected_broker, extracted = extract_holdings_from_image(image_bytes, file.content_type)
    except PortfolioExtractionError as exc:
        upload.status = "failed"
        upload.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        logger.exception("Unexpected error extracting portfolio upload %s", upload.id)
        upload.status = "failed"
        upload.error_message = "Unexpected error while reading the screenshot"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while reading the screenshot",
        ) from exc

    if not extracted:
        upload.status = "failed"
        upload.error_message = "No holdings could be found in this screenshot."
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=upload.error_message)

    # A broker the user typed in explicitly wins over what we detected.
    broker = broker or detected_broker
    upload.broker = broker

    matched, skipped = match_holdings(extracted)
    if not matched:
        upload.status = "failed"
        upload.error_message = "No fully visible holdings could be read from this screenshot."
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=upload.error_message)

    merge_holdings_into_portfolio(db, current_user.id, upload.id, broker, matched)

    upload.status = "success"
    upload.holdings_found = len(matched)
    db.commit()

    result = _build_portfolio_out(db, current_user.id)
    result.skipped = skipped
    result.upload_broker = broker
    result.upload_holdings = len(matched)
    return result


@router.post("/holdings", response_model=schemas.PortfolioHoldingOut, status_code=status.HTTP_201_CREATED)
def add_holding(
    payload: schemas.PortfolioHoldingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.resolved_url and payload.quantity:
        company_key = canonical_company_key(payload.resolved_url)
        same_company = [
            h
            for h in db.query(models.PortfolioHolding).filter(models.PortfolioHolding.user_id == current_user.id)
            if h.resolved_url and canonical_company_key(h.resolved_url) == company_key
        ]
        # Add to the row without a broker (the manual one) if there is one; otherwise to
        # the only row for this company. If it is held at several brokers we can't tell
        # which one the purchase belongs to, so it becomes its own row.
        existing = next((h for h in same_company if not h.broker), None)
        if existing is None and len(same_company) == 1:
            existing = same_company[0]
        if existing is not None:
            _add_shares_to_existing(existing, payload.quantity, payload.avg_price)
            db.commit()
            db.refresh(existing)
            return existing

    holding = models.PortfolioHolding(
        user_id=current_user.id,
        raw_name=payload.company_name.strip(),
        quantity=payload.quantity,
        avg_price=payload.avg_price,
        ltp=payload.ltp,
        invested_value=payload.invested_value
        if payload.invested_value is not None
        else (payload.quantity * payload.avg_price if payload.quantity and payload.avg_price else None),
        current_value=payload.current_value,
        pnl=payload.pnl,
        resolved_name=payload.resolved_name,
        resolved_url=payload.resolved_url,
    )
    if holding.resolved_url and holding.ltp is None:
        ticker = prices.ticker_from_url(holding.resolved_url)
        price, is_approximate = prices.fetch_price_for_holding(ticker, holding.resolved_url)
        if price is not None:
            prices.apply_price(holding, price, is_approximate)
            holding.price_synced_at = datetime.now(timezone.utc)
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


@router.post("/sync", response_model=schemas.PortfolioOut)
def sync_prices(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    holdings = db.query(models.PortfolioHolding).filter(models.PortfolioHolding.user_id == current_user.id).all()

    # Holdings saved before their company could be matched have no ticker to price,
    # so retry the match now rather than leaving them stuck forever.
    for h in holdings:
        if not h.resolved_url:
            match = resolve_company(h.raw_name)
            if match:
                h.resolved_name = match["name"]
                h.resolved_url = match["url"]
    db.flush()

    latest = prices.fetch_prices_for_holdings(holdings)

    now = datetime.now(timezone.utc)
    unsynced = []
    for h in holdings:
        price, is_approximate = latest.get(h.id, (None, False))
        if price is None:
            unsynced.append(h.raw_name)
            continue
        prices.apply_price(h, price, is_approximate)
        h.price_synced_at = now
    db.commit()

    result = _build_portfolio_out(db, current_user.id)
    result.unsynced = unsynced
    return result


@router.patch("/holdings/{holding_id}", response_model=schemas.PortfolioHoldingOut)
def update_holding(
    holding_id: int,
    payload: schemas.PortfolioHoldingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    holding = _get_owned_holding(db, current_user.id, holding_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(holding, field, value)

    # Buying/selling shares: keep invested, current value and P&L consistent with
    # the new quantity, unless the user typed those figures in directly.
    if holding.quantity:
        if "invested_value" not in changes and ("quantity" in changes or "avg_price" in changes):
            if holding.avg_price is not None:
                holding.invested_value = round(holding.quantity * holding.avg_price, 2)
        if "current_value" not in changes and ("quantity" in changes or "ltp" in changes):
            if holding.ltp is not None:
                holding.current_value = round(holding.quantity * holding.ltp, 2)
    if "pnl" not in changes and holding.current_value is not None and holding.invested_value is not None:
        holding.pnl = round(holding.current_value - holding.invested_value, 2)
    db.commit()
    db.refresh(holding)
    return holding


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(
    holding_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    holding = _get_owned_holding(db, current_user.id, holding_id)
    db.delete(holding)
    db.commit()


@router.get("/uploads", response_model=list[schemas.PortfolioUploadSummaryOut])
def list_uploads(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.PortfolioUpload)
        .filter(models.PortfolioUpload.user_id == current_user.id)
        .order_by(models.PortfolioUpload.uploaded_at.desc())
        .all()
    )


def _add_shares_to_existing(holding: models.PortfolioHolding, quantity: float, buy_price: float | None) -> None:
    """Buying more of a stock already held: add the shares and blend the average price."""
    old_quantity = holding.quantity or 0
    old_invested = holding.invested_value
    if old_invested is None:
        old_invested = old_quantity * (holding.avg_price or 0)

    holding.quantity = old_quantity + quantity
    if buy_price is not None:
        holding.invested_value = round(old_invested + quantity * buy_price, 2)
        holding.avg_price = holding.invested_value / holding.quantity
    elif holding.avg_price is not None:
        holding.invested_value = round(holding.quantity * holding.avg_price, 2)
    if holding.ltp is not None:
        holding.current_value = round(holding.quantity * holding.ltp, 2)
    if holding.current_value is not None and holding.invested_value is not None:
        holding.pnl = round(holding.current_value - holding.invested_value, 2)


def _get_owned_holding(db: Session, user_id: int, holding_id: int) -> models.PortfolioHolding:
    holding = (
        db.query(models.PortfolioHolding)
        .filter(models.PortfolioHolding.id == holding_id, models.PortfolioHolding.user_id == user_id)
        .first()
    )
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return holding


def _build_portfolio_out(db: Session, user_id: int) -> schemas.PortfolioOut:
    holdings = (
        db.query(models.PortfolioHolding)
        .filter(models.PortfolioHolding.user_id == user_id)
        .order_by(models.PortfolioHolding.raw_name)
        .all()
    )

    total_invested = 0.0
    total_current_value = 0.0
    total_pnl = 0.0
    for h in holdings:
        invested, current, pnl = holding_amounts(h)
        total_invested += invested
        total_current_value += current
        total_pnl += pnl

    last_upload = (
        db.query(models.PortfolioUpload)
        .filter(models.PortfolioUpload.user_id == user_id, models.PortfolioUpload.status == "success")
        .order_by(models.PortfolioUpload.uploaded_at.desc())
        .first()
    )

    synced_times = [h.price_synced_at for h in holdings if h.price_synced_at]

    return schemas.PortfolioOut(
        last_synced_at=max(synced_times) if synced_times else None,
        holdings=holdings,
        summary=schemas.PortfolioSummaryOut(
            total_invested=round(total_invested, 2),
            total_current_value=round(total_current_value, 2),
            total_pnl=round(total_pnl, 2),
            holding_count=len(holdings),
        ),
        last_upload_at=last_upload.uploaded_at if last_upload else None,
    )


def _save_upload(user_id: int, content_type: str, data: bytes) -> str:
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(content_type, "")
    folder = os.path.join(config.PORTFOLIO_UPLOAD_DIR, str(user_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    return path
