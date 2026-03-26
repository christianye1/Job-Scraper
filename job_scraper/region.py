from __future__ import annotations

from job_scraper.models import JobListing

_REMOTE_HINTS = (
    "remote",
    "hybrid",
    "work from home",
    "wfh",
    "home office",
    "teilweise remote",
    "hybrides arbeiten",
)

_GERMANY_HINTS = (
    "germany",
    "deutschland",
    "berlin",
    "brandenburg",
    "hamburg",
    "münchen",
    "munich",
    "frankfurt",
    "köln",
    "cologne",
    "düsseldorf",
    "nrw",
    "baden-württemberg",
    "bayern",
    "hessen",
    "sachsen",
    "dach",
)


def _hay(job: JobListing) -> str:
    parts = [job.location or "", job.title or "", job.team or ""]
    return "\n".join(parts).casefold()


def passes_location_needles(job: JobListing, needles: list[str]) -> bool:
    if not needles:
        return False
    hay = _hay(job)
    return any(n.strip() and n.casefold() in hay for n in needles)


def is_remote_germany(job: JobListing) -> bool:
    """Remote / hybrid AND tied to Germany (or DACH) in the same text."""
    hay = _hay(job)
    if not any(h in hay for h in _REMOTE_HINTS):
        return False
    return any(h in hay for h in _GERMANY_HINTS)


def passes_region_filter(job: JobListing, needles: list[str], *, remote_germany: bool) -> bool:
    """
    Keep job if it matches any location needle OR (when enabled) remote+Germany hints.
    If both needles and remote_germany are off, caller should skip filtering.
    """
    if passes_location_needles(job, needles):
        return True
    if remote_germany and is_remote_germany(job):
        return True
    return False
