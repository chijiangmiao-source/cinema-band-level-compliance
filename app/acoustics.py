"""A-weighted octave-band acoustics: weighting, energy summation, adjudication."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

# A-weighting corrections (dB) for each octave-band centre frequency (Hz).
A_WEIGHTS_DB: dict[int, Decimal] = {
    63: Decimal("-26.2"),
    125: Decimal("-16.1"),
    250: Decimal("-8.6"),
    500: Decimal("-3.2"),
    1000: Decimal("0.0"),
    2000: Decimal("1.2"),
    4000: Decimal("1.0"),
    8000: Decimal("-1.1"),
}

FREQUENCIES_HZ: tuple[int, ...] = tuple(A_WEIGHTS_DB)


def weighted_level_db(level_db: Decimal, frequency_hz: int) -> Decimal:
    """L_i + A_i for one band, computed with exact decimal arithmetic."""
    return level_db + A_WEIGHTS_DB[frequency_hz]


def band_energy(weighted_db: Decimal) -> float:
    """Linear energy-like contribution of a band: 10 ** (L / 10)."""
    return 10.0 ** (float(weighted_db) / 10.0)


def combine_levels(levels_db: dict[int, Decimal]) -> float:
    """Total level 10*log10(sum 10**((L_i+A_i)/10)); never rounded here."""
    total_energy = sum(
        band_energy(weighted_level_db(level, frequency))
        for frequency, level in levels_db.items()
    )
    return 10.0 * math.log10(total_energy)


def verdict_for(total_db: float, limit_db: float) -> str:
    """Adjudicate the *unrounded* total against the limit (inclusive)."""
    return "COMPLIANT" if total_db <= limit_db else "NON_COMPLIANT"


def round_to_centidb(value_db: float) -> float:
    """Round half-up to 0.01 dB. Used for display only, never for verdicts."""
    cents = Decimal(str(value_db)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(cents)
