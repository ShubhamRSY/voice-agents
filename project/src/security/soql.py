"""Salesforce SOQL literal helpers."""

from __future__ import annotations

import re

_SOQL_FIELD = frozenset({"Email", "Phone"})
_SAFE_LITERAL = re.compile(r"^[\w.@+\-() ]+$")


def contact_lookup_query(identifier: str) -> str:
    """Build a SOQL contact lookup; field and value are validated/escaped."""
    fields = "Id,Email,FirstName,LastName,Phone"
    is_email = "@" in identifier
    field = "Email" if is_email else "Phone"
    if field not in _SOQL_FIELD:
        raise ValueError("invalid SOQL field")
    if not identifier or len(identifier) > 255 or not _SAFE_LITERAL.match(identifier):
        raise ValueError("invalid contact identifier")
    escaped = identifier.replace("'", "''")
    # Field is allowlisted; literal is validated and single-quote escaped.
    return f"SELECT {fields} FROM Contact WHERE {field} = '{escaped}' LIMIT 1"  # nosec B608
