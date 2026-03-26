from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from job_scraper.filters import matches_target_role
from job_scraper.models import JobListing

_RSS_URL = "https://rss.indeed.com/rss"
_STRIP_HTML = re.compile(r"<[^>]+>")


def _tag_local(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _plain(html: str) -> str:
    return _STRIP_HTML.sub(" ", html or "")


def _indeed_external_id(guid: str | None, link: str) -> str:
    if guid:
        g = guid.strip()
        if g.startswith("http"):
            q = parse_qs(urlparse(g).query)
            jk = q.get("jk")
            if jk and jk[0]:
                return jk[0]
        if len(g) < 200:
            return g
    q = parse_qs(urlparse(link).query)
    jk = q.get("jk")
    if jk and jk[0]:
        return jk[0]
    return unquote(link)


def _parse_rss_items(xml_bytes: bytes) -> list[tuple[str, str, str, str | None]]:
    root = ET.fromstring(xml_bytes)
    out: list[tuple[str, str, str, str | None]] = []
    for child in root:
        if _tag_local(child.tag) != "channel":
            continue
        for item in child:
            if _tag_local(item.tag) != "item":
                continue
            title = ""
            link = ""
            description = ""
            guid: str | None = None
            for el in item:
                t = _tag_local(el.tag)
                text = (el.text or "").strip()
                if t == "title":
                    title = text
                elif t == "link":
                    link = text
                elif t == "description":
                    description = text
                elif t == "guid":
                    guid = text or None
            if title and link:
                out.append((title, link, description, guid))
    return out


async def fetch_indeed_search(client: httpx.AsyncClient, q: str, l: str, label: str) -> list[JobListing]:
    q, l, label = q.strip(), (l or "").strip(), (label or "").strip() or q[:48]
    params: dict[str, str] = {"q": q}
    if l:
        params["l"] = l
    r = await client.get(_RSS_URL, params=params, timeout=45.0, follow_redirects=True)
    r.raise_for_status()
    body = r.content
    head = body[:800].decode("utf-8", errors="replace").lower()
    if b"Just a moment" in body or "<rss" not in head:
        raise RuntimeError(
            "Indeed did not return RSS (often blocked by Cloudflare for scripted requests). "
            "Try from a normal browser network, reduce frequency, or rely on other sources."
        )
    items = _parse_rss_items(body)
    listings: list[JobListing] = []
    for title, link, description, guid in items:
        desc_plain = _plain(description)
        if not matches_target_role(title, desc_plain):
            continue
        eid = _indeed_external_id(guid, link)
        listings.append(
            JobListing(
                source="indeed",
                board=label,
                external_id=eid,
                title=title.strip(),
                url=link.strip(),
                location=l or None,
                team=None,
            )
        )
    return listings
