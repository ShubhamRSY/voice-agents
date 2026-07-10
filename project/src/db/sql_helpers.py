"""Safe SQL fragment builders for allowlisted dynamic UPDATE statements."""

from __future__ import annotations

import re
from collections.abc import Iterable

_COL_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def build_set_clause(columns: Iterable[str], allowed: frozenset[str]) -> str:
    """Build ``col = ?, ...`` from an allowlisted column set (values bound separately)."""
    cols = list(columns)
    for col in cols:
        if col not in allowed:
            raise ValueError(f"disallowed column: {col}")
        if not _COL_RE.match(col):
            raise ValueError(f"invalid column name: {col}")
    # Column names validated against allowlist — values use parameter binding.
    return ", ".join(f"{col} = ?" for col in cols)
