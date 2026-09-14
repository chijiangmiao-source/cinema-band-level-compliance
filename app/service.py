"""Assessment orchestration: weighting, summation, adjudication, ordering."""

from __future__ import annotations

from decimal import Decimal

from .acoustics import (
    A_WEIGHTS_DB,
    FREQUENCIES_HZ,
    band_energy,
    combine_levels,
    round_to_centidb,
    subtract_background_db,
    verdict_for,
    weighted_level_db,
)
from .errors import ApiError
from .models import AssessmentResponse, BandResult


def assess(
    levels_db: dict[int, Decimal],
    limit_db: Decimal,
    background_db: dict[int, Decimal] | None = None,
) -> AssessmentResponse:
    corrected_db: dict[int, float] | None = None
    if background_db is not None:
        corrected_db = _subtract_background(levels_db, background_db)

    # The effective measurement feeds the existing weighting, summation,
    # ordering and adjudication chain unchanged; without a background file
    # it is simply the submitted measurement. Corrected levels are wrapped
    # back into exact decimals via their shortest repr, so float() of the
    # weighted level is bit-identical to the computed float.
    effective: dict[int, Decimal] = (
        levels_db
        if corrected_db is None
        else {f: Decimal(str(corrected_db[f])) for f in FREQUENCIES_HZ}
    )

    weighted = {f: weighted_level_db(effective[f], f) for f in FREQUENCIES_HZ}

    # The verdict always uses the unrounded total; rounding is display-only.
    total_db = combine_levels(effective)
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
            background_db=(
                float(background_db[f]) if background_db is not None else None
            ),
            corrected_level_db=(
                corrected_db[f] if corrected_db is not None else None
            ),
        )
        for f in ordered
    ]

    return AssessmentResponse(
        total_db=round_to_centidb(total_db),
        limit_db=limit_float,
        verdict=verdict_for(total_db, limit_float),
        bands=bands,
    )


def _subtract_background(
    levels_db: dict[int, Decimal], background_db: dict[int, Decimal]
) -> dict[int, float]:
    """Per-band linear energy subtraction. The whole request is rejected
    unless the background is strictly quieter than the measurement in
    every band; otherwise there is no positive residual energy to take
    the logarithm of."""
    failures: list[int] = []
    corrected: dict[int, float] = {}
    for frequency in FREQUENCIES_HZ:
        residual = None
        if background_db[frequency] < levels_db[frequency]:
            residual = subtract_background_db(
                levels_db[frequency], background_db[frequency]
            )
        if residual is None:
            failures.append(frequency)
        else:
            corrected[frequency] = residual

    if failures:
        raise ApiError(
            422,
            "BACKGROUND_NOT_LOWER",
            "Background level must be lower than the measured level in every "
            "octave band; cannot take the logarithm of non-positive "
            "residual energy.",
            {
                "bands": [
                    {
                        "frequency_hz": f,
                        "level_db": float(levels_db[f]),
                        "background_db": float(background_db[f]),
                    }
                    for f in failures
                ]
            },
        )
    return corrected
