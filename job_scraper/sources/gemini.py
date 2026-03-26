from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import quote_plus

import httpx

from job_scraper.filters import matches_target_role
from job_scraper.models import JobListing

_BASE_PROMPT = """You are helping compile a job-search digest for a candidate. Your knowledge cutoff applies; supplement with likely still-open roles recruiters post in Germany.

Geography: Greater Berlin, Brandenburg, and Germany-scoped remote/hybrid (not generic worldwide remote unless the listing explicitly says Germany or Berlin area).

Role focus: internships, working students (Werkstudent), new graduate, associate, junior, entry-level positions in software engineering, machine learning, ML engineering, and AI engineering.

Sources to reflect (do not claim you scraped live pages; synthesize from knowledge and typical postings): LinkedIn Jobs, Indeed Germany, StepStone, and notable company career sites reachable via search.

Return ONLY a JSON array (no markdown fences, no commentary). Maximum 24 objects. Each object MUST have:
- "company": string (employer name)
- "title": string (job title)
- "apply_url": string (HTTPS URL to the job posting or official application page ONLY if you are reasonably confident it is real; otherwise use empty string "")
- "salary": string or null (e.g. "EUR 60k-70k" or null if unknown)
- "location": string (city/region or "Remote (Germany)" style)
- "source_hint": one of "linkedin", "indeed", "stepstone", "company_site", "other"

Rules:
- Prefer well-known companies hiring in Berlin/Brandenburg when possible.
- Do NOT fabricate specific application URLs. Use "" for apply_url unless you are sure.
- Include a short mix of internships and new-grad/entry roles matching the technical focus.
"""


def _extract_json_array(text: str) -> list[Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("jobs", "listings", "items", "results", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    raise ValueError("Gemini response must be a JSON array or an object containing a jobs array")


def _stable_id(company: str, title: str, url: str) -> str:
    h = hashlib.sha256(f"{company}|{title}|{url}".encode("utf-8")).hexdigest()
    return h[:22]


async def fetch_gemini_suggestions(api_key: str, model: str, prompt_extra: str | None) -> list[JobListing]:
    print(f"Gemini: calling API (model={model})…", flush=True)
    full_text = _BASE_PROMPT
    if prompt_extra and prompt_extra.strip():
        full_text += "\n\nAdditional instructions from user config:\n" + prompt_extra.strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body: dict[str, Any] = {
        "contents": [{"parts": [{"text": full_text}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, params={"key": api_key}, json=body)
        r.raise_for_status()
        payload = r.json()

    parts = ((payload.get("candidates") or [{}])[0].get("content", {}).get("parts")) or []
    raw_text = ""
    for p in parts:
        if isinstance(p, dict) and "text" in p:
            raw_text += p.get("text") or ""
    if not raw_text.strip():
        raise RuntimeError("Gemini returned empty text")

    rows = _extract_json_array(raw_text)
    out: list[JobListing] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or "").strip()
        title = str(row.get("title") or "").strip()
        loc = str(row.get("location") or "").strip() or None
        salary_raw = row.get("salary")
        salary = None if salary_raw is None else str(salary_raw).strip() or None
        src_hint = str(row.get("source_hint") or "other").strip() or "other"
        url_s = str(row.get("apply_url") or "").strip()

        if not company or not title:
            continue
        if not matches_target_role(title, None):
            continue

        job_url = url_s if url_s.startswith("http") else ""
        if not job_url:
            job_url = "https://www.google.com/search?q=" + quote_plus(f"{company} {title} jobs Berlin")
        eid = _stable_id(company, title, job_url)
        if eid in seen:
            continue
        seen.add(eid)

        board_label = f"gemini-{src_hint}"
        out.append(
            JobListing(
                source="gemini",
                board=board_label,
                external_id=eid,
                title=title,
                url=job_url,
                location=loc,
                team=src_hint,
                company=company,
                salary=salary,
            )
        )
    print(f"Gemini: parsed {len(out)} listing(s) from model (region filters apply with other sources next).", flush=True)
    return out
