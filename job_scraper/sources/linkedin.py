from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from job_scraper.filters import matches_target_role
from job_scraper.models import JobListing

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_URN_RE = re.compile(r"urn:li:jobPosting:(\d+)")


async def fetch_linkedin_search(
    client: httpx.AsyncClient,
    keywords: str,
    location: str,
    label: str,
    *,
    pages: int = 2,
    page_delay_s: float = 0.6,
) -> list[JobListing]:
    keywords = keywords.strip()
    location = (location or "").strip()
    label = (label or "").strip() or keywords[:48]
    pages = max(1, min(pages, 10))
    listings: list[JobListing] = []
    seen_ids: set[str] = set()

    for page_idx in range(pages):
        start = page_idx * 25
        params: dict[str, str | int] = {
            "keywords": keywords,
            "location": location,
            "start": start,
        }
        r = await client.get(_SEARCH_URL, params=params, timeout=45.0, follow_redirects=True)
        r.raise_for_status()
        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.job-search-card")
        if not cards:
            break
        page_added = 0
        for div in cards:
            urn = div.get("data-entity-urn") or ""
            m = _URN_RE.search(urn)
            if not m:
                continue
            job_id = m.group(1)
            if job_id in seen_ids:
                continue
            a = div.select_one("a.base-card__full-link")
            href = (a.get("href") or "").split("?")[0].strip() if a else ""
            h3 = div.select_one("h3.base-search-card__title")
            title = h3.get_text(strip=True) if h3 else ""
            if not title or not href:
                continue
            if not matches_target_role(title, None):
                continue
            loc_el = div.select_one("span.job-search-card__location")
            loc = loc_el.get_text(strip=True) if loc_el else None
            company_el = div.select_one("h4.base-search-card__subtitle")
            company = company_el.get_text(strip=True) if company_el else None
            seen_ids.add(job_id)
            listings.append(
                JobListing(
                    source="linkedin",
                    board=label,
                    external_id=job_id,
                    title=title,
                    url=href,
                    location=loc,
                    team=None,
                    company=company,
                    salary=None,
                )
            )
            page_added += 1
        if page_added == 0:
            break
        if page_idx + 1 < pages:
            await asyncio.sleep(page_delay_s)
    return listings
