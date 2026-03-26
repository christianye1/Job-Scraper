from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobListing:
    source: str
    board: str
    external_id: str
    title: str
    url: str
    location: str | None
    team: str | None

    @property
    def fingerprint(self) -> str:
        return f"{self.source}:{self.board}:{self.external_id}"
