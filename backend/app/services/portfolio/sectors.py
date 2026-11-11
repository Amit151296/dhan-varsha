"""Looks up a company's sector and industry from its screener.in page, caching
the result in the database so each company is only fetched once.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from sqlalchemy.orm import Session

from app import config, models
from app.services.company.analyzer import canonical_company_key

logger = logging.getLogger(__name__)

BASE_URL = "https://www.screener.in"
MAX_WORKERS = 4

# <a href="/market/IN05/IN0501/" title="Sector">Financial Services</a>
_LINK = re.compile(r'<a[^>]*href="/market/[^"]*"[^>]*title="(Sector|Industry)"[^>]*>\s*([^<]*?)\s*</a>')


def parse_sector_and_industry(html: str) -> tuple[str | None, str | None]:
    found = {title: text for title, text in _LINK.findall(html) if text}
    return found.get("Sector"), found.get("Industry")


def _fetch_from_screener(company_url: str) -> tuple[str | None, str | None]:
    if not config.SCREENER_SESSIONS:
        return None, None
    session = config.SCREENER_SESSIONS[0]
    headers = {"Cookie": f"csrftoken={session['csrf_token']}; sessionid={session['session_id']}"}
    try:
        response = requests.get(
            f"{BASE_URL}{company_url}", headers=headers, timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Could not fetch sector for %s", company_url, exc_info=True)
        return None, None
    return parse_sector_and_industry(response.text)


def get_sectors(db: Session, company_urls: list[str]) -> dict[str, tuple[str, str | None]]:
    """Maps canonical company URL -> (sector, industry) for every URL we could classify.

    URLs that can't be classified (page unreachable, no sector listed) are simply
    absent from the result and are retried next time.
    """
    keys = list(dict.fromkeys(canonical_company_key(u) for u in company_urls if u))
    if not keys:
        return {}

    cached = db.query(models.CompanySector).filter(models.CompanySector.company_url.in_(keys)).all()
    result = {row.company_url: (row.sector, row.industry) for row in cached}

    missing = [key for key in keys if key not in result]
    if missing:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            fetched = list(pool.map(_fetch_from_screener, missing))
        for key, (sector, industry) in zip(missing, fetched):
            if sector:
                db.add(models.CompanySector(company_url=key, sector=sector, industry=industry))
                result[key] = (sector, industry)
        db.commit()
    return result
