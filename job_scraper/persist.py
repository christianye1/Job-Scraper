from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from job_scraper.models import JobListing


def _listing_dict(j: JobListing) -> dict[str, object]:
    return {
        "source": j.source,
        "board": j.board,
        "external_id": j.external_id,
        "title": j.title,
        "url": j.url,
        "location": j.location,
        "team": j.team,
        "fingerprint": j.fingerprint,
    }


def _md_cell(s: str | None) -> str:
    if not s:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def write_run_outputs(
    *,
    json_path: Path,
    md_path: Path,
    listings: list[JobListing],
    new_count: int,
) -> None:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "generated_at_utc": generated,
        "matched_count": len(listings),
        "new_since_state_count": new_count,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "jobs": [_listing_dict(j) for j in listings],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Job listings (latest run)",
        "",
        f"UTC: `{generated}` · **{len(listings)}** matched this fetch · **{new_count}** were new vs saved state.",
        "",
        "Regenerate with `python -m job_scraper`. This file is overwritten each run.",
        "",
        "| Source | Board | Title | Location | Link |",
        "|--------|-------|-------|----------|------|",
    ]
    for j in listings:
        link = f"[Apply]({j.url})" if j.url else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(j.source),
                    _md_cell(j.board),
                    _md_cell(j.title),
                    _md_cell(j.location),
                    link.replace("|", "\\|"),
                ]
            )
            + " |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
