"""Assessment orchestration: weighting, summation, adjudication, ordering."""

from __future__ import annotations

from decimal import Decimal

from .acoustics import (
    A_WEIGHTS_DB,
    FREQUENCIES_HZ,
    band_energy,
    combine_levels,
    round_to_centidb,
    verdict_for,
    weighted_level_db,
)
from .models import AssessmentResponse, BandResult


def assess(levels_db: dict[int, Decimal], limit_db: Decimal) -> AssessmentResponse:
    weighted = {f: weighted_level_db(levels_db[f], f) for f in FREQUENCIES_HZ}

    # The verdict always uses the unrounded total; rounding is display-only.
    total_db = combine_levels(levels_db)
    limit_float = float(limit_db)

    # Energy is monotonic in the (exact decimal) weighted level, so ordering
    # by weighted level descending is ordering by energy contribution
    # descending; exact decimal ties fall back to ascending frequency.
    ordered = sorted(FREQUENCIES_HZ, key=lambda f: (-weighted[f], f))
    bands = [
        BandResult(
            frequency_hz=f,
            level_db=float(levels_db[f]),
            a_weight_db=float(A_WEIGHTS_DB[f]),
            weighted_level_db=float(weighted[f]),
            energy=band_energy(weighted[f]),
        )
        for f in ordered
    ]

    return AssessmentResponse(
        total_db=round_to_centidb(total_db),
        limit_db=limit_float,
        verdict=verdict_for(total_db, limit_float),
        bands=bands,
    )
