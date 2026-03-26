from __future__ import annotations

import httpx

from job_scraper.filters import matches_target_role
from job_scraper.models import JobListing


def _company_from_slug(company: str) -> str:
    return company.replace("-", " ").replace("_", " ").strip().title() or company


async def fetch_lever_board(client: httpx.AsyncClient, company: str) -> list[JobListing]:
    url = f"https://api.lever.co/v0/postings/{company}"
    r = await client.get(url, params={"mode": "json"}, timeout=30.0)
    r.raise_for_status()
    jobs = r.json()
    if not isinstance(jobs, list):
        return []
    display_company = _company_from_slug(company)
    out: list[JobListing] = []
    for j in jobs:
        jid = str(j.get("id") or "")
        title = (j.get("text") or "").strip()
        if not jid or not title:
            continue
        desc = (j.get("descriptionPlain") or j.get("description") or "") or ""
        if not matches_target_role(title, desc):
            continue
        loc = ""
        categories = j.get("categories") or {}
        if isinstance(categories, dict):
            loc = (categories.get("location") or "").strip()
        hosted = (j.get("hostedUrl") or "").strip()
        apply = (j.get("applyUrl") or "").strip()
        job_url = hosted or apply
        out.append(
            JobListing(
                source="lever",
                board=company,
                external_id=jid,
                title=title,
                url=job_url,
                location=loc or None,
                team=None,
                company=display_company,
                salary=None,
            )
        )
    return out
