"""Shared helpers: build CSV payloads and compute expectations from the
specification formula, so tests never assert against canned responses."""

from __future__ import annotations

import math
from decimal import Decimal

from app.acoustics import A_WEIGHTS_DB, FREQUENCIES_HZ


def make_csv(
    levels: dict[int, str],
    *,
    header: str = "frequency_hz,level_db",
    newline: str = "\r\n",
    order: list[int] | None = None,
) -> bytes:
    freqs = order if order is not None else list(FREQUENCIES_HZ)
    lines = [header]
    lines += [f"{f},{levels[f]}" for f in freqs]
    return (newline.join(lines) + newline).encode("utf-8")


def weighted_levels(levels: dict[int, str | float]) -> dict[int, Decimal]:
    return {f: Decimal(str(levels[f])) + A_WEIGHTS_DB[f] for f in FREQUENCIES_HZ}


def expected_total_db(levels: dict[int, str | float]) -> float:
    weighted = weighted_levels(levels)
    return 10.0 * math.log10(
        sum(10.0 ** (float(weighted[f]) / 10.0) for f in FREQUENCIES_HZ)
    )


def expected_band_order(levels: dict[int, str | float]) -> list[int]:
    weighted = weighted_levels(levels)
    return sorted(FREQUENCIES_HZ, key=lambda f: (-weighted[f], f))


def corrected_levels(
    levels: dict[int, str], background: dict[int, str]
) -> dict[int, float]:
    """Residual level per band after background subtraction, per the
    specification formula 10*log10(10**(L/10) - 10**(B/10))."""
    return {
        f: 10.0
        * math.log10(
            10.0 ** (float(levels[f]) / 10.0)
            - 10.0 ** (float(background[f]) / 10.0)
        )
        for f in FREQUENCIES_HZ
    }
