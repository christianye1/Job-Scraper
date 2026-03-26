from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from job_scraper.career_tier import career_tier
from job_scraper.models import JobListing


def _listing_dict(j: JobListing) -> dict[str, object]:
    return {
        "source": j.source,
        "board": j.board,
        "external_id": j.external_id,
        "company": j.company,
        "title": j.title,
        "url": j.url,
        "location": j.location,
        "team": j.team,
        "salary": j.salary,
        "fingerprint": j.fingerprint,
        "career_tier": career_tier(j.title),
    }


def _md_cell(s: str | None) -> str:
    if not s:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def _md_table_rows(listings: list[JobListing]) -> list[str]:
    lines = [
        "| Company | Title | Location | Salary | Source | Link |",
        "|---------|-------|----------|--------|--------|------|",
    ]
    for j in listings:
        link = f"[Apply]({j.url})" if j.url else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(j.company),
                    _md_cell(j.title),
                    _md_cell(j.location),
                    _md_cell(j.salary),
                    _md_cell(j.source),
                    link.replace("|", "\\|"),
                ]
            )
            + " |"
        )
    return lines


def _split_by_tier(listings: list[JobListing]) -> tuple[list[JobListing], list[JobListing], list[JobListing]]:
    intern_l: list[JobListing] = []
    new_grad_l: list[JobListing] = []
    other_l: list[JobListing] = []
    for j in listings:
        t = career_tier(j.title)
        if t == "intern":
            intern_l.append(j)
        elif t == "new_grad":
            new_grad_l.append(j)
        else:
            other_l.append(j)
    return intern_l, new_grad_l, other_l


def write_run_outputs(
    *,
    json_path: Path,
    md_path: Path,
    listings: list[JobListing],
    new_count: int,
) -> None:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    intern_l, new_grad_l, other_l = _split_by_tier(listings)
    counts = {"intern": len(intern_l), "new_grad": len(new_grad_l), "other": len(other_l)}
    meta = {
        "generated_at_utc": generated,
        "matched_count": len(listings),
        "new_since_state_count": new_count,
        "counts_by_tier": counts,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "intern": [_listing_dict(j) for j in intern_l],
        "new_grad": [_listing_dict(j) for j in new_grad_l],
        "other": [_listing_dict(j) for j in other_l],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Job listings (latest run)",
        "",
        f"UTC: `{generated}` · **{len(listings)}** matched this fetch · **{new_count}** were new vs saved state.",
        f"**Internships:** {counts['intern']} · **New grad / entry level:** {counts['new_grad']} · **Other:** {counts['other']}",
        "",
        "Regenerate with `python -m job_scraper`. This file is overwritten each run.",
        "",
    ]
    sections: tuple[tuple[str, str, list[JobListing]], ...] = (
        ("Internships", "intern", intern_l),
        ("New grad / entry level", "new_grad", new_grad_l),
        ("Other matches", "other", other_l),
    )
    for heading, _key, rows in sections:
        if not rows:
            continue
        lines.append(f"## {heading} ({len(rows)})")
        lines.append("")
        lines.extend(_md_table_rows(rows))
        lines.append("")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
