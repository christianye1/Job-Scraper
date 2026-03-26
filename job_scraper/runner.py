from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from job_scraper.models import JobListing
from job_scraper.persist import write_run_outputs
from job_scraper.sources import (
    fetch_greenhouse_board,
    fetch_indeed_search,
    fetch_lever_board,
    fetch_linkedin_search,
)
from job_scraper.state import load_seen, save_seen

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = _ROOT / "config" / "boards.json"
DEFAULT_STATE = _ROOT / "data" / "seen_jobs.json"
_DEFAULT_OUT_DIR = _ROOT / "data" / "output"
DEFAULT_JSON_OUT = _DEFAULT_OUT_DIR / "jobs_latest.json"
DEFAULT_MD_OUT = _DEFAULT_OUT_DIR / "jobs.md"

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _load_board_config(path: Path) -> tuple[
    list[str],
    list[str],
    list[tuple[str, str, str]],
    list[tuple[str, str, str, int]],
    list[str],
]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    gh = raw.get("greenhouse") or []
    lv = raw.get("lever") or []
    if not isinstance(gh, list) or not isinstance(lv, list):
        raise ValueError("boards.json must have 'greenhouse' and 'lever' string arrays")
    greenhouse_boards = [str(x).strip() for x in gh if str(x).strip()]
    lever_boards = [str(x).strip() for x in lv if str(x).strip()]

    warnings: list[str] = []
    indeed_rows: list[tuple[str, str, str]] = []
    raw_indeed = raw.get("indeed")
    if raw_indeed is None:
        raw_indeed = []
    elif not isinstance(raw_indeed, list):
        raise ValueError("boards.json 'indeed' must be an array when present")
    for i, row in enumerate(raw_indeed):
        if not isinstance(row, dict):
            warnings.append(f"indeed[{i}]: expected JSON object, skipped")
            continue
        q = str(row.get("q", "")).strip()
        if not q:
            warnings.append(f"indeed[{i}]: missing 'q', skipped")
            continue
        loc = str(row.get("l", "") or "").strip()
        label = str(row.get("label", "") or "").strip()
        indeed_rows.append((q, loc, label))

    linkedin_rows: list[tuple[str, str, str, int]] = []
    raw_li = raw.get("linkedin")
    if raw_li is None:
        raw_li = []
    elif not isinstance(raw_li, list):
        raise ValueError("boards.json 'linkedin' must be an array when present")
    for i, row in enumerate(raw_li):
        if not isinstance(row, dict):
            warnings.append(f"linkedin[{i}]: expected JSON object, skipped")
            continue
        keywords = str(row.get("keywords", "")).strip()
        if not keywords:
            warnings.append(f"linkedin[{i}]: missing 'keywords', skipped")
            continue
        loc = str(row.get("location", "") or "").strip()
        label = str(row.get("label", "") or "").strip()
        try:
            pages = int(row.get("pages", 2))
        except (TypeError, ValueError):
            pages = 2
        linkedin_rows.append((keywords, loc, label, pages))

    return greenhouse_boards, lever_boards, indeed_rows, linkedin_rows, warnings


async def _collect_all(
    client: httpx.AsyncClient, boards_path: Path
) -> tuple[list[JobListing], list[str], list[str]]:
    greenhouse_boards, lever_boards, indeed_rows, linkedin_rows, pre_warnings = _load_board_config(boards_path)
    tasks: list[tuple[str, asyncio.Task[list[JobListing]]]] = []
    for b in greenhouse_boards:
        t = asyncio.create_task(fetch_greenhouse_board(client, b))
        tasks.append((f"greenhouse:{b}", t))
    for b in lever_boards:
        t = asyncio.create_task(fetch_lever_board(client, b))
        tasks.append((f"lever:{b}", t))
    for q, loc, label in indeed_rows:
        lab = label or q[:32]
        t = asyncio.create_task(fetch_indeed_search(client, q, loc, lab))
        tasks.append((f"indeed:{lab}", t))
    for keywords, loc, label, pages in linkedin_rows:
        lab = label or keywords[:32]
        t = asyncio.create_task(fetch_linkedin_search(client, keywords, loc, lab, pages=pages))
        tasks.append((f"linkedin:{lab}", t))
    listings: list[JobListing] = []
    errors: list[str] = []
    for label, t in tasks:
        try:
            listings.extend(await t)
        except Exception as e:
            errors.append(f"{label}: {e}")
    listings.sort(key=lambda j: (j.source, j.board, j.title.lower()))
    return listings, errors, pre_warnings


def _format_line(j: JobListing) -> str:
    loc = f" | {j.location}" if j.location else ""
    return f"[{j.source}:{j.board}] {j.title}{loc}\n   {j.url}"


async def run_async(
    boards_path: Path,
    state_path: Path,
    only_new: bool,
    *,
    json_out: Path | None,
    md_out: Path | None,
) -> int:
    seen = load_seen(state_path)
    async with httpx.AsyncClient(headers={"User-Agent": _BROWSER_UA}, follow_redirects=True) as client:
        listings, errors, cfg_warnings = await _collect_all(client, boards_path)
    for msg in cfg_warnings:
        print(f"Config: {msg}", flush=True)
    for msg in errors:
        print(f"Warning: {msg}", flush=True)
    new_on_this_run = [j for j in listings if j.fingerprint not in seen]
    if only_new:
        to_show = new_on_this_run
    else:
        to_show = listings
    for j in to_show:
        print(_format_line(j))
        print()
    seen.update(j.fingerprint for j in listings)
    save_seen(state_path, seen)
    if json_out is not None and md_out is not None:
        write_run_outputs(
            json_path=json_out,
            md_path=md_out,
            listings=listings,
            new_count=len(new_on_this_run),
        )
        print(f"Wrote {json_out} and {md_out}", flush=True)
    print(f"Total matched this run: {len(listings)} | New since last state: {len(new_on_this_run)}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fetch SWE/ML/AI intern and entry-level jobs (Greenhouse, Lever, Indeed RSS, LinkedIn guest search)."
    )
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to boards.json")
    p.add_argument("--state", type=Path, default=DEFAULT_STATE, help="Path to seen job ids JSON")
    p.add_argument("--all", action="store_true", help="List all current matches, not only new since last run")
    p.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_OUT,
        help="Write full matched snapshot as JSON",
    )
    p.add_argument(
        "--md-out",
        type=Path,
        default=DEFAULT_MD_OUT,
        help="Write full matched snapshot as Markdown",
    )
    p.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write data/output snapshot files (stdout only, besides seen_jobs.json)",
    )
    args = p.parse_args()
    only_new = not args.all
    json_out: Path | None = None if args.no_save else args.json_out
    md_out: Path | None = None if args.no_save else args.md_out
    raise SystemExit(asyncio.run(run_async(args.config, args.state, only_new, json_out=json_out, md_out=md_out)))


if __name__ == "__main__":
    main()
