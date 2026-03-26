from __future__ import annotations

import re
from typing import Literal

Tier = Literal["intern", "new_grad", "other"]

_INTERNSHIP = re.compile(
    r"(?:"
    r"\binternship\b|"
    r"co[- ]?op\b|"
    r"\bintern\b|"
    r"\bpraktikum\b|"
    r"\bwerkstudent(?:in)?\b|"
    r"\bwerkstudium\b"
    r")",
    re.IGNORECASE,
)

_NEW_GRAD = re.compile(
    r"(?:"
    r"\bnew\s+grad(?:uate)?\b|"
    r"entry[\s-]?level|"
    r"\bjunior\b|"
    r"\bassociate\s+engineer\b|"
    r"\bassociate\s+developer\b|"
    r"\bassociate\s+scientist\b|"
    r"early\s+career|"
    r"university\s+grad|"
    r"recent\s+graduate|"
    r"\bgraduate\s+(?:engineer|developer|programme|program|scheme|role|position)\b|"
    r"\bfresh\s+grad"
    r")",
    re.IGNORECASE,
)


def career_tier(title: str) -> Tier:
    """Intern vs new-grad bucket from title. Intern wins when both could match."""
    t = title or ""
    if _INTERNSHIP.search(t):
        return "intern"
    if _NEW_GRAD.search(t):
        return "new_grad"
    return "other"
