"""A-weighted octave-band acoustics: weighting, energy summation, adjudication."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext

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


def subtract_background_db(level_db: Decimal, background_db: Decimal) -> float:
    """Residual band level after subtracting the background's linear energy:
    10*log10(10**(L/10) - 10**(B/10)). Requires B < L.

    Computed as L + 10*log10(1 - 10**((B-L)/10)) in decimal arithmetic whose
    precision scales with the gap between the two levels, so any strictly
    positive gap stays meaningful — floats would collapse a gap below
    ~1e-16 to zero and wrongly suggest a non-positive residual energy.
    """
    # Digit budget for the exact difference of the two inputs: from the
    # highest significant digit down to the lowest one, plus guard.
    span = (
        max(level_db.adjusted(), background_db.adjusted())
        - min(level_db.as_tuple().exponent, background_db.as_tuple().exponent)
        + 2
    )
    with localcontext() as ctx:
        ctx.prec = max(28, span)
        delta = (background_db - level_db) / 10  # strictly negative, exact
        # 1 - 10**delta first differs from 1 around digit -delta.adjusted();
        # keep ~25 significant digits beyond that for a float-exact result.
        ctx.prec = max(ctx.prec, 25 - delta.adjusted())
        residual_ratio = 1 - (delta * Decimal(10).ln()).exp()
        corrected = level_db + 10 * residual_ratio.log10()
    return float(corrected)


def combine_levels(levels_db: dict[int, Decimal]) -> float:
    """Total level 10*log10(sum 10**((L_i+A_i)/10)); never rounded here.

    Evaluated as peak + 10*log10(sum 10**((w_i-peak)/10)): identical in
    exact arithmetic, but bands far below the loudest (possible after
    background subtraction) cannot underflow the sum to zero.
    """
    weighted = [
        float(weighted_level_db(level, frequency))
        for frequency, level in levels_db.items()
    ]
    peak = max(weighted)
    total_energy = sum(10.0 ** ((w - peak) / 10.0) for w in weighted)
    return peak + 10.0 * math.log10(total_energy)


def verdict_for(total_db: float, limit_db: float) -> str:
    """Adjudicate the *unrounded* total against the limit (inclusive)."""
    return "COMPLIANT" if total_db <= limit_db else "NON_COMPLIANT"


def round_to_centidb(value_db: float) -> float:
    """Round half-up to 0.01 dB. Used for display only, never for verdicts."""
    cents = Decimal(str(value_db)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(cents)
