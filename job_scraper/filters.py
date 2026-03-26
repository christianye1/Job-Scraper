from __future__ import annotations

import re

# Tune these lists for your targets.
ROLE_KEYWORDS = (
    r"\bsoftware\s+engineer\b",
    r"\bsoftware\s+engineering\b",
    r"\bswe\b",
    r"\bsde\b",
    r"\bdeveloper\b",
    r"\bmachine\s+learning\b",
    r"\bml\s+engineer",
    r"\bdeep\s+learning\b",
    r"\bai\s+engineer",
    r"\bartificial\s+intelligence\b",
    r"\bapplied\s+scientist\b",
    r"\bresearch\s+engineer\b",
)

LEVEL_KEYWORDS = (
    r"\bintern",
    r"\binternship\b",
    r"\bnew\s+grad",
    r"\bentry[\s-]?level\b",
    r"\bjunior\b",
    r"\bassociate\b",
    r"\bearly\s+career\b",
    r"\buniversity\s+grad",
    r"\brecent\s+graduate\b",
    r"\bcampus\b",
    r"\bgraduate\b",
    r"\bstudent\b",
    r"\bco-?op\b",
)


def _compile_group(patterns: tuple[str, ...]) -> re.Pattern[str]:
    inner = "|".join(f"(?:{p})" for p in patterns)
    return re.compile(inner, re.IGNORECASE)


_ROLE_RE = _compile_group(ROLE_KEYWORDS)
_LEVEL_RE = _compile_group(LEVEL_KEYWORDS)


def matches_target_role(title: str, text: str | None = None) -> bool:
    """True if listing looks like SWE / ML / AI at intern or entry level."""
    haystack = title if not text else f"{title}\n{text}"
    if not _ROLE_RE.search(haystack):
        return False
    if not _LEVEL_RE.search(haystack):
        return False
    return True
