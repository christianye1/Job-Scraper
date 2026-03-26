from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from job_scraper.career_tier import career_tier
from job_scraper.models import JobListing
from job_scraper.persist import write_run_outputs
from job_scraper.region import passes_region_filter
from job_scraper.sources import (
    fetch_gemini_suggestions,
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
    list[str],
    bool,
    bool,
    str,
    str | None,
]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_filter = raw.get("location_filter")
    if raw_filter is None:
        location_filter: list[str] = []
    elif isinstance(raw_filter, list):
        location_filter = [str(x).strip() for x in raw_filter if str(x).strip()]
    else:
        raise ValueError("boards.json 'location_filter' must be an array of strings when present")
    remote_germany = bool(raw.get("remote_germany", False))
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

    gemini_enabled = False
    gemini_model = "gemini-2.0-flash"
    gemini_prompt_extra: str | None = None
    raw_gem = raw.get("gemini")
    if isinstance(raw_gem, dict):
        gemini_enabled = bool(raw_gem.get("enabled", False))
        gemini_model = str(raw_gem.get("model") or gemini_model).strip() or gemini_model
        extra = raw_gem.get("prompt_extra")
        if extra is not None and str(extra).strip():
            gemini_prompt_extra = str(extra).strip()
    elif raw_gem is True:
        gemini_enabled = True

    return (
        greenhouse_boards,
        lever_boards,
        indeed_rows,
        linkedin_rows,
        warnings,
        location_filter,
        remote_germany,
        gemini_enabled,
        gemini_model,
        gemini_prompt_extra,
    )


async def _collect_all(
    client: httpx.AsyncClient, boards_path: Path
) -> tuple[list[JobListing], list[str], list[str]]:
    (
        greenhouse_boards,
        lever_boards,
        indeed_rows,
        linkedin_rows,
        pre_warnings,
        location_filter,
        remote_germany,
        gemini_enabled,
        gemini_model,
        gemini_prompt_extra,
    ) = _load_board_config(boards_path)
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
    if gemini_enabled:
        gkey = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not gkey:
            pre_warnings = [
                *pre_warnings,
                "gemini: enabled in boards.json but GEMINI_API_KEY is not set; skipped",
            ]
        else:
            t = asyncio.create_task(fetch_gemini_suggestions(gkey, gemini_model, gemini_prompt_extra))
            tasks.append(("gemini", t))
    gemini_scheduled = any(lab == "gemini" for lab, _ in tasks)
    listings: list[JobListing] = []
    errors: list[str] = []
    for label, t in tasks:
        try:
            listings.extend(await t)
        except Exception as e:
            errors.append(f"{label}: {e}")
    if location_filter or remote_germany:
        before = len(listings)
        listings = [
            j for j in listings if passes_region_filter(j, location_filter, remote_germany=remote_germany)
        ]
        print(
            f"Region filter needles={location_filter!r} remote_germany={remote_germany}: "
            f"kept {len(listings)}/{before}",
            flush=True,
        )
    if gemini_scheduled:
        g_n = sum(1 for j in listings if j.source == "gemini")
        print(f"Gemini: {g_n} listing(s) left after merging with other sources + region filters.", flush=True)
    listings.sort(
        key=lambda j: ((j.company or "").lower(), j.source, j.title.lower()),
    )
    return listings, errors, pre_warnings


def _format_line(j: JobListing) -> str:
    co = f"{j.company} — " if j.company else ""
    loc = f" | {j.location}" if j.location else ""
    sal = f" | {j.salary}" if j.salary else ""
    return f"[{j.source}] {co}{j.title}{loc}{sal}\n   {j.url}"


async def run_async(
    boards_path: Path,
    state_path: Path,
    only_new: bool,
    *,
    json_out: Path | None,
    md_out: Path | None,
) -> int:
    seen_before = load_seen(state_path)
    async with httpx.AsyncClient(headers={"User-Agent": _BROWSER_UA}, follow_redirects=True) as client:
        listings, errors, cfg_warnings = await _collect_all(client, boards_path)
    for msg in cfg_warnings:
        print(f"Config: {msg}", flush=True)
    for msg in errors:
        print(f"Warning: {msg}", flush=True)
    new_on_this_run = [j for j in listings if j.fingerprint not in seen_before]
    if only_new:
        to_show = new_on_this_run
    else:
        to_show = listings
    buckets: dict[str, list[JobListing]] = {"intern": [], "new_grad": [], "other": []}
    for j in to_show:
        buckets[career_tier(j.title)].append(j)
    section_titles = (
        ("intern", "Internships"),
        ("new_grad", "New grad / entry level"),
        ("other", "Other matches"),
    )
    printed_any = False
    for key, title in section_titles:
        chunk = buckets[key]
        if not chunk:
            continue
        printed_any = True
        print(f"\n=== {title} ({len(chunk)}) ===\n", flush=True)
        for j in chunk:
            print(_format_line(j))
            print()
    if not printed_any:
        print("(No jobs to show for this run.)\n", flush=True)
    # Replace state with this run only — drop fingerprints for jobs that vanished so nothing stale accumulates.
    save_seen(state_path, {j.fingerprint for j in listings})
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
    load_dotenv(_ROOT / ".env")
    p = argparse.ArgumentParser(
        description="Fetch SWE/ML/AI intern and entry-level jobs (ATS APIs, Indeed, LinkedIn, optional Gemini)."
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
