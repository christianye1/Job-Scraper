from __future__ import annotations

import re

import httpx

from job_scraper.filters import matches_target_role
from job_scraper.models import JobListing

_STRIP_HTML = re.compile(r"<[^>]+>")


def _plain(text: str | None) -> str:
    if not text:
        return ""
    return _STRIP_HTML.sub(" ", text)


async def fetch_greenhouse_board(client: httpx.AsyncClient, board: str) -> list[JobListing]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
    r = await client.get(url, params={"content": "true"}, timeout=30.0)
    r.raise_for_status()
    payload = r.json()
    jobs = payload.get("jobs") or []
    out: list[JobListing] = []
    for j in jobs:
        jid = str(j.get("id", ""))
        title = (j.get("title") or "").strip()
        content = _plain(j.get("content"))
        if not jid or not title:
            continue
        if not matches_target_role(title, content):
            continue
        loc_bits = []
        for loc in j.get("offices") or []:
            name = (loc.get("name") or "").strip()
            if name:
                loc_bits.append(name)
        location = ", ".join(loc_bits) if loc_bits else None
        dept = j.get("departments") or []
        team = None
        if dept and isinstance(dept[0], dict):
            team = (dept[0].get("name") or "").strip() or None
        absolute_url = (j.get("absolute_url") or "").strip()
        out.append(
            JobListing(
                source="greenhouse",
                board=board,
                external_id=jid,
                title=title,
                url=absolute_url,
                location=location,
                team=team,
            )
        )
    return out
