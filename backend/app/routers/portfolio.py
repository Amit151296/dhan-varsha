import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.exceptions import PortfolioExtractionError
from app.services.company.analyzer import canonical_company_key
from app.services.portfolio import prices, sectors
from app.services.portfolio.analysis import analyse_portfolio, holding_amounts
from app.services.portfolio.extractor import extract_holdings_from_image
from app.services.portfolio.matcher import match_holdings, resolve_company
from app.services.portfolio.merge import merge_holdings_into_portfolio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.get("", response_model=schemas.PortfolioOut)
def get_portfolio(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return _build_portfolio_out(db, current_user.id)


@router.get("/analysis", response_model=schemas.PortfolioAnalysisOut)
def get_portfolio_analysis(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    holdings = db.query(models.PortfolioHolding).filter(models.PortfolioHolding.user_id == current_user.id).all()
    company_sectors = sectors.get_sectors(db, [h.resolved_url for h in holdings if h.resolved_url])
    return analyse_portfolio(holdings, company_sectors)


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
