"""Looks up a company's sector and industry from its screener.in page, caching
the result in the database so each company is only fetched once.
"""

from __future__ import annotations

import html as html_lib
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


# screener.in files these industries under a broader sector (Capital Goods, Consumer Durables);
# we show them as their own sector. Matching on industry covers every company in it, not just
# the ones held today.
INDUSTRY_SECTOR_OVERRIDES = {
    "aerospace & defense": "Defence",
    "gems, jewellery and watches": "Gems & Jewellery",
}


def _apply_override(sector: str, industry: str | None) -> str:
    return INDUSTRY_SECTOR_OVERRIDES.get((industry or "").casefold(), sector)


_INDUSTRY_HREF = re.compile(r'<a[^>]*href="(/market/[^"]*)"[^>]*title="Industry"')


def parse_sector_and_industry(html: str) -> tuple[str | None, str | None]:
    found = {title: html_lib.unescape(text) for title, text in _LINK.findall(html) if text}
    return found.get("Sector"), found.get("Industry")


def parse_industry_url(html: str) -> str | None:
    match = _INDUSTRY_HREF.search(html)
    return f"{BASE_URL}{match.group(1)}" if match else None


def _fetch_from_screener(company_url: str) -> tuple[str | None, str | None, str | None]:
    """(sector, industry, industry listing URL) from one company page."""
    if not config.SCREENER_SESSIONS:
        return None, None, None
    session = config.SCREENER_SESSIONS[0]
    headers = {"Cookie": f"csrftoken={session['csrf_token']}; sessionid={session['session_id']}"}
    try:
        response = requests.get(
            f"{BASE_URL}{company_url}", headers=headers, timeout=config.SCREENER_REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Could not fetch sector for %s", company_url, exc_info=True)
        return None, None, None
    sector, industry = parse_sector_and_industry(response.text)
    return sector, industry, parse_industry_url(response.text)


def get_sectors(db: Session, company_urls: list[str]) -> dict[str, tuple[str, str | None]]:
    """Maps canonical company URL -> (sector, industry) for every URL we could classify.

    URLs that can't be classified (page unreachable, no sector listed) are simply
    absent from the result and are retried next time.
    """
    keys = list(dict.fromkeys(canonical_company_key(u) for u in company_urls if u))
    if not keys:
        return {}

    cached = db.query(models.CompanySector).filter(models.CompanySector.company_url.in_(keys)).all()
    # Older rows were saved with HTML entities still in them ("Aerospace &amp; Defense").
    result = {
        row.company_url: (
            _apply_override(html_lib.unescape(row.sector), html_lib.unescape(row.industry or "")),
            html_lib.unescape(row.industry) if row.industry else None,
        )
        for row in cached
    }

    missing = [key for key in keys if key not in result]
    if missing:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            fetched = list(pool.map(_fetch_from_screener, missing))
        known_links = {
            row.company_url
            for row in db.query(models.CompanyIndustryLink).filter(models.CompanyIndustryLink.company_url.in_(missing))
        }
        for key, (sector, industry, industry_url) in zip(missing, fetched):
            if sector:
                db.add(models.CompanySector(company_url=key, sector=sector, industry=industry))
                result[key] = (_apply_override(sector, industry), industry)
            # The same page names the industry listing the metrics table needs, so save it now
            # and the metrics fetch never has to open this company page a second time.
            if industry_url and key not in known_links:
                db.add(models.CompanyIndustryLink(company_url=key, industry_url=industry_url))
        db.commit()
    return result
