"""Merges one screenshot's extracted+matched holdings into a user's single
consolidated portfolio.

A row's identity is the company (its canonical screener.in URL, falling back
to the case-insensitive name) *plus the broker*. Re-uploading the same
broker's screen therefore refreshes its rows in place, while the same company
held at two brokers stays as two separate rows - they are different positions
(different quantity, average price, account) and must not be summed together.
A row with no broker label (an older upload, or one added by hand) is claimed
by the first upload that names a broker for that company.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.services.company.analyzer import canonical_company_key


def _identity(resolved_url: str | None, name: str) -> str:
    if resolved_url:
        return "url:" + canonical_company_key(resolved_url).casefold()
    return "name:" + name.strip().casefold()


def _broker_key(broker: str | None) -> str:
    return (broker or "").strip().casefold()


def merge_holdings_into_portfolio(
    db: Session, user_id: int, upload_id: int, broker: str | None, matched_holdings: list[dict]
) -> None:
    existing = db.query(models.PortfolioHolding).filter(models.PortfolioHolding.user_id == user_id).all()
    existing_by_key = {
        (_identity(row.resolved_url, row.raw_name), _broker_key(row.broker)): row for row in existing
    }

    for holding in matched_holdings:
        identity = _identity(holding["resolved_url"], holding["company_name"])
        key = (identity, _broker_key(broker))

        row = existing_by_key.get(key)
        if row is None and broker:
            row = existing_by_key.pop((identity, ""), None)
        if row is None:
            row = models.PortfolioHolding(user_id=user_id, raw_name=holding["company_name"])
            db.add(row)
        existing_by_key[key] = row

        row.source_upload_id = upload_id
        row.broker = broker or row.broker
        row.raw_name = holding["company_name"]
        row.quantity = holding["quantity"]
        row.avg_price = holding["avg_price"]
        row.ltp = holding["ltp"]
        row.invested_value = holding["invested_value"]
        row.current_value = holding["current_value"]
        row.pnl = holding["pnl"]
        row.resolved_name = holding["resolved_name"] or row.resolved_name
        row.resolved_url = holding["resolved_url"] or row.resolved_url
