"""Variant configuration.
Set CHALLENGE_VARIANT=alpha|beta|gamma|delta|epsilon via .env.

Note for candidates: the underlying code is identical across variants. This
file (and the variant lists in config/variants/) is used by the interview
panel to scope which subset of issues a given candidate's review is expected
to cover - it does not change runtime behavior."""

import os
from pathlib import Path

_VARIANTS_DIR = Path(__file__).resolve().parent / "variants"
_ACTIVE: set[str] | None = None


def _load_active_flaws() -> set[str]:
    global _ACTIVE
    if _ACTIVE is not None:
        return _ACTIVE
    variant = os.getenv("CHALLENGE_VARIANT", "alpha").lower()
    path = _VARIANTS_DIR / f"{variant}.txt"
    if path.exists():
        _ACTIVE = set(line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#"))
    else:
        _ACTIVE = set()
    return _ACTIVE


def is_flaw_active(flaw_id: str) -> bool:
    """Check if this flaw is in-scope for the current variant."""
    return flaw_id in _load_active_flaws()


def get_active_flaws() -> set[str]:
    """Return set of in-scope flaw IDs for the current variant."""
    return _load_active_flaws().copy()
