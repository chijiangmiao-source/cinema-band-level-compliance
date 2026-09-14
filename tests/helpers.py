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
    trailing_blank_lines: int = 0,
) -> bytes:
    freqs = order if order is not None else list(FREQUENCIES_HZ)
    lines = [header]
    lines += [f"{f},{levels[f]}" for f in freqs]
    lines += [""] * trailing_blank_lines
    return (newline.join(lines) + newline).encode("utf-8")


def weighted_levels(levels: dict[int, str]) -> dict[int, Decimal]:
    return {f: Decimal(levels[f]) + A_WEIGHTS_DB[f] for f in FREQUENCIES_HZ}


def expected_total_db(levels: dict[int, str]) -> float:
    weighted = weighted_levels(levels)
    return 10.0 * math.log10(
        sum(10.0 ** (float(weighted[f]) / 10.0) for f in FREQUENCIES_HZ)
    )


def expected_band_order(levels: dict[int, str]) -> list[int]:
    weighted = weighted_levels(levels)
    return sorted(FREQUENCIES_HZ, key=lambda f: (-weighted[f], f))
