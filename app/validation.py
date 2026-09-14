"""Validation of the allowed-total-level (limit) multipart field."""

from __future__ import annotations

import re
from decimal import Decimal

from .errors import ApiError

MIN_LIMIT_DB = Decimal("0")
MAX_LIMIT_DB = Decimal("140")

# Plain decimal notation with at most two decimal places. This rejects NaN,
# infinities, scientific notation, hex, signs, underscores, thousands
# separators and non-ASCII digits by construction.
_LIMIT_RE = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")


def parse_limit(raw: str) -> Decimal:
    """Parse the limit; only plain decimals in [0, 140] with <= 2 decimals."""
    if not _LIMIT_RE.fullmatch(raw):
        raise ApiError(
            422,
            "INVALID_LIMIT",
            "limit must be a plain decimal number in [0, 140] dB with at most "
            "two decimal places; NaN, infinities and other notations are rejected.",
            {"value": raw},
        )
    value = Decimal(raw)
    if not (MIN_LIMIT_DB <= value <= MAX_LIMIT_DB):
        raise ApiError(
            422,
            "INVALID_LIMIT",
            "limit must be within [0, 140] dB.",
            {"value": raw},
        )
    return value
