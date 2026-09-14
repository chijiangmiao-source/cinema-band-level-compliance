"""End-to-end API tests: computation, adjudication, ordering, validation.

Expected values are recomputed from the specification formula in
``tests/helpers.py``; nothing asserts against a fixed/canned response.
"""

import math

import pytest

from app.acoustics import A_WEIGHTS_DB, FREQUENCIES_HZ
from app.csv_parser import MAX_CSV_BYTES
from helpers import (
    expected_band_order,
    expected_total_db,
    make_csv,
    weighted_levels,
)

URL = "/api/v1/assessments"

LEVELS = {
    63: "80",
    125: "78",
    250: "85",
    500: "88",
    1000: "90",
    2000: "86",
    4000: "82",
    8000: "75",
}


def post_assessment(client, csv_bytes: bytes, limit: str):
    return client.post(
        URL,
        files={"file": ("bands.csv", csv_bytes, "text/csv")},
        data={"limit": limit},
    )


def test_healthcheck(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_valid_assessment_compliant(client):
    total = expected_total_db(LEVELS)
    limit = math.ceil(total) + 5  # comfortably above the computed total
    response = post_assessment(client, make_csv(LEVELS), str(limit))

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "COMPLIANT"
    # Displayed total is the unrounded value rounded to 0.01 dB.
    assert abs(body["total_db"] - total) <= 0.005 + 1e-9
    assert body["limit_db"] == float(limit)

    weighted = weighted_levels(LEVELS)
    assert [b["frequency_hz"] for b in body["bands"]] == expected_band_order(LEVELS)
    for band in body["bands"]:
        freq = band["frequency_hz"]
        assert band["level_db"] == float(LEVELS[freq])
        assert band["a_weight_db"] == float(A_WEIGHTS_DB[freq])
        assert band["weighted_level_db"] == pytest.approx(float(weighted[freq]))
        assert band["energy"] == pytest.approx(
            10.0 ** (float(weighted[freq]) / 10.0), rel=1e-12
        )
    # Energy contributions arrive in non-increasing order.
    energies = [b["energy"] for b in body["bands"]]
    assert energies == sorted(energies, reverse=True)


def test_valid_assessment_non_compliant(client):
    total = expected_total_db(LEVELS)
    limit = math.floor(total) - 5  # comfortably below the computed total
    response = post_assessment(client, make_csv(LEVELS), str(limit))
    assert response.status_code == 200
    assert response.json()["verdict"] == "NON_COMPLIANT"


def test_verdict_flips_with_limit_around_total(client):
    total = expected_total_db(LEVELS)
    below = math.floor(total * 100) / 100
    above = below + 0.01
    assert below < total < above  # sanity: total is not on a centi-dB boundary

    low = post_assessment(client, make_csv(LEVELS), f"{below:.2f}")
    high = post_assessment(client, make_csv(LEVELS), f"{above:.2f}")
    assert low.json()["verdict"] == "NON_COMPLIANT"
    assert high.json()["verdict"] == "COMPLIANT"
    # Same measurement, same displayed total: adjudication used the unrounded value.
    assert low.json()["total_db"] == high.json()["total_db"]


def test_boundary_adjudication_end_to_end(client):
    levels = {f: "0" for f in FREQUENCIES_HZ}
    total = expected_total_db(levels)
    below = math.floor(total * 100) / 100
    above = below + 0.01
    assert below < total < above

    assert (
        post_assessment(client, make_csv(levels), f"{below:.2f}").json()["verdict"]
        == "NON_COMPLIANT"
    )
    assert (
        post_assessment(client, make_csv(levels), f"{above:.2f}").json()["verdict"]
        == "COMPLIANT"
    )


def test_equal_energy_contributions_ordered_by_frequency(client):
    levels = {f: "0" for f in FREQUENCIES_HZ}
    levels[500] = "53.2"  # 53.2 + (-3.2) = 50.0 dB weighted
    levels[1000] = "50"  # 50 + 0.0    = 50.0 dB weighted -> exact tie
    expected = expected_band_order(levels)
    assert expected[:2] == [500, 1000]

    response = post_assessment(client, make_csv(levels), "140")
    assert response.status_code == 200
    bands = response.json()["bands"]
    assert [b["frequency_hz"] for b in bands] == expected
    assert bands[0]["energy"] == pytest.approx(bands[1]["energy"])


def test_lf_newlines_and_shuffled_rows_accepted(client):
    shuffled = make_csv(
        LEVELS, newline="\n", order=[8000, 63, 1000, 500, 250, 2000, 4000, 125]
    )
    canonical = post_assessment(client, make_csv(LEVELS), "140")
    shuffled_response = post_assessment(client, shuffled, "140")
    assert shuffled_response.status_code == 200
    assert shuffled_response.json()["total_db"] == canonical.json()["total_db"]


@pytest.mark.parametrize(
    "bad_limit",
    [
        "nan",
        "NaN",
        "inf",
        "-inf",
        "Infinity",
        "1e2",
        "0x50",
        " 90",
        "90 ",
        "+90",
        "-0.01",
        "90.",
        ".5",
        "9.999",
        "140.01",
        "141",
        "1_0",
        "１２３",  # full-width digits
        "1,5",
        "",
    ],
)
def test_invalid_limit_rejected(client, bad_limit):
    response = post_assessment(client, make_csv(LEVELS), bad_limit)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_LIMIT"
    assert set(body["error"]) == {"code", "message", "details"}


@pytest.mark.parametrize("good_limit", ["0", "0.00", "90", "90.5", "90.05", "140", "140.00"])
def test_valid_limit_accepted(client, good_limit):
    response = post_assessment(client, make_csv(LEVELS), good_limit)
    assert response.status_code == 200
    assert response.json()["limit_db"] == float(good_limit)


@pytest.mark.parametrize(
    "level_value",
    ["nan", "inf", "1e2", "-1", "140.01", "abc", "", " 80", "1_0"],
)
def test_invalid_csv_level_rejected(client, level_value):
    levels = dict(LEVELS)
    levels[250] = level_value
    response = post_assessment(client, make_csv(levels), "140")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_LEVEL"


@pytest.mark.parametrize(
    "payload,code",
    [
        (make_csv(LEVELS, header="Frequency_Hz,level_db"), "INVALID_HEADER"),
        (b"\xef\xbb\xbf" + make_csv(LEVELS), "INVALID_HEADER"),
        (b"frequency_hz,level_db\r\n63,\xff\xfe\r\n", "INVALID_ENCODING"),
        (
            make_csv(
                {f: LEVELS[f] for f in FREQUENCIES_HZ[:-1]},
                order=list(FREQUENCIES_HZ[:-1]),
            ),
            "INVALID_ROW_COUNT",
        ),
        (
            make_csv(LEVELS, order=list(FREQUENCIES_HZ[:-1]) + [63]),
            "DUPLICATE_FREQUENCY",
        ),
        (
            make_csv({**LEVELS, 63.5: "80"}, order=[63.5] + list(FREQUENCIES_HZ[1:])),
            "UNKNOWN_FREQUENCY",
        ),
    ],
    ids=[
        "bad-header",
        "bom",
        "bad-encoding",
        "seven-rows",
        "duplicate-band",
        "unknown-band",
    ],
)
def test_whole_file_validation_errors(client, payload, code):
    response = post_assessment(client, payload, "100")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert set(body) == {"error"}


def test_oversized_file_rejected_with_413(client):
    payload = make_csv(LEVELS, trailing_blank_lines=0)
    payload += b"\n" * (MAX_CSV_BYTES + 1 - len(payload))
    response = post_assessment(client, payload, "100")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_exactly_64_kib_file_accepted(client):
    payload = make_csv(LEVELS)
    payload += b"\n" * (MAX_CSV_BYTES - len(payload))  # blank lines are ignored
    assert len(payload) == MAX_CSV_BYTES
    response = post_assessment(client, payload, "140")
    assert response.status_code == 200


def test_missing_file_field_rejected(client):
    response = client.post(URL, data={"limit": "90"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MISSING_FILE"


def test_missing_limit_field_rejected(client):
    response = client.post(
        URL, files={"file": ("bands.csv", make_csv(LEVELS), "text/csv")}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MISSING_LIMIT"


def test_different_inputs_give_different_totals(client):
    louder = dict(LEVELS)
    louder[1000] = "120"
    quiet = post_assessment(client, make_csv(LEVELS), "140").json()
    loud = post_assessment(client, make_csv(louder), "140").json()
    assert loud["total_db"] > quiet["total_db"]
