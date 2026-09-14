"""Unit tests for the acoustics core: weighting, summation, adjudication."""

import math
from decimal import Decimal, localcontext

import pytest

from app.acoustics import (
    A_WEIGHTS_DB,
    FREQUENCIES_HZ,
    band_energy,
    combine_levels,
    round_to_centidb,
    subtract_background_db,
    verdict_for,
    weighted_level_db,
)


def test_a_weights_match_specification():
    assert FREQUENCIES_HZ == (63, 125, 250, 500, 1000, 2000, 4000, 8000)
    assert A_WEIGHTS_DB == {
        63: Decimal("-26.2"),
        125: Decimal("-16.1"),
        250: Decimal("-8.6"),
        500: Decimal("-3.2"),
        1000: Decimal("0.0"),
        2000: Decimal("1.2"),
        4000: Decimal("1.0"),
        8000: Decimal("-1.1"),
    }


def test_weighted_level_is_exact_decimal_sum():
    # Exactness matters: ties in energy contribution must be real ties.
    assert weighted_level_db(Decimal("53.2"), 500) == Decimal("50.0")
    assert weighted_level_db(Decimal("80.05"), 63) == Decimal("53.85")


def test_band_energy_is_linear_power_ratio():
    assert band_energy(Decimal("50.0")) == pytest.approx(1e5)
    assert band_energy(Decimal("0.0")) == pytest.approx(1.0)


def test_combine_all_bands_at_equal_weighted_level():
    # Every band weighted to exactly 80 dB -> total = 80 + 10*log10(8).
    levels = {
        63: Decimal("106.2"),
        125: Decimal("96.1"),
        250: Decimal("88.6"),
        500: Decimal("83.2"),
        1000: Decimal("80"),
        2000: Decimal("78.8"),
        4000: Decimal("79"),
        8000: Decimal("81.1"),
    }
    expected = 80.0 + 10.0 * math.log10(8.0)
    assert combine_levels(levels) == pytest.approx(expected, abs=1e-9)


def test_combine_matches_specification_formula():
    levels = {
        63: Decimal("80"),
        125: Decimal("78"),
        250: Decimal("85"),
        500: Decimal("88"),
        1000: Decimal("90"),
        2000: Decimal("86"),
        4000: Decimal("82"),
        8000: Decimal("75"),
    }
    expected = 10.0 * math.log10(
        sum(10.0 ** (float(levels[f] + A_WEIGHTS_DB[f]) / 10.0) for f in levels)
    )
    assert combine_levels(levels) == pytest.approx(expected, abs=1e-9)


def test_combine_levels_does_not_underflow_for_very_quiet_bands():
    # Weighted levels around -3300 dB: 10**(w/10) underflows to 0.0 in
    # float, but the total must still be computed, not crash on log10(0).
    levels = {f: Decimal("-3300") for f in FREQUENCIES_HZ}
    expected = -3300.0 + 10.0 * math.log10(
        sum(10.0 ** (float(A_WEIGHTS_DB[f]) / 10.0) for f in FREQUENCIES_HZ)
    )
    assert combine_levels(levels) == pytest.approx(expected, abs=1e-9)


def test_subtract_background_matches_spec_formula():
    expected = 10.0 * math.log10(10.0**9 - 10.0**8.5)
    result = subtract_background_db(Decimal("90"), Decimal("85"))
    assert result == pytest.approx(expected, rel=1e-12)


def test_subtract_background_gap_below_float_resolution():
    # A 1e-20 dB gap: floats see both levels as exactly 90.0, yet the
    # residual level must still be computed per the spec formula.
    with localcontext() as ctx:
        ctx.prec = 60
        residual = Decimal(10) ** Decimal(9) - Decimal(10) ** (
            Decimal("89.99999999999999999999") / 10
        )
        expected = float(10 * residual.log10())
    result = subtract_background_db(Decimal("90"), Decimal("89.99999999999999999999"))
    assert -117 < expected < -116  # sanity: tiny gap, deeply negative residual
    assert result == pytest.approx(expected, rel=1e-12)


def test_verdict_boundary_is_inclusive():
    assert verdict_for(90.0, 90.0) == "COMPLIANT"
    assert verdict_for(math.nextafter(90.0, math.inf), 90.0) == "NON_COMPLIANT"
    assert verdict_for(math.nextafter(90.0, -math.inf), 90.0) == "COMPLIANT"


def test_display_rounding_is_half_up_to_centidb():
    assert round_to_centidb(1.005) == 1.01
    assert round_to_centidb(89.030899868) == 89.03
    assert round_to_centidb(90.0) == 90.0
