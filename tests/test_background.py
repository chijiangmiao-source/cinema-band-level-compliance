"""End-to-end tests for optional background-noise subtraction.

Expected values are recomputed from the specification formula in
``tests/helpers.py``; nothing asserts against a fixed/canned response.
"""

import math

import pytest

from app.acoustics import A_WEIGHTS_DB, FREQUENCIES_HZ
from app.csv_parser import MAX_CSV_BYTES
from helpers import (
    corrected_levels,
    expected_band_order,
    expected_total_db,
    make_csv,
    weighted_levels,
)

URL = "/api/v1/assessments"

MAIN = {
    63: "80",
    125: "78",
    250: "85",
    500: "88",
    1000: "90",
    2000: "86",
    4000: "82",
    8000: "75",
}
BACKGROUND = {
    63: "70",
    125: "68",
    250: "75",
    500: "80",
    1000: "85",
    2000: "78",
    4000: "72",
    8000: "65",
}


def post_assessment(client, csv_bytes: bytes, limit: str, background_bytes=None):
    files = {"file": ("bands.csv", csv_bytes, "text/csv")}
    if background_bytes is not None:
        files["background_file"] = ("background.csv", background_bytes, "text/csv")
    return client.post(URL, files=files, data={"limit": limit})


def test_background_subtraction_matches_spec_formula(client):
    corrected = corrected_levels(MAIN, BACKGROUND)
    total = expected_total_db(corrected)
    limit = math.ceil(total) + 5  # comfortably above the corrected total
    response = post_assessment(client, make_csv(MAIN), str(limit), make_csv(BACKGROUND))

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "COMPLIANT"
    # The reported total is the corrected total, rounded to 0.01 dB.
    assert abs(body["total_db"] - total) <= 0.005 + 1e-9
    assert body["limit_db"] == float(limit)

    weighted = weighted_levels(corrected)
    assert [b["frequency_hz"] for b in body["bands"]] == expected_band_order(corrected)
    for band in body["bands"]:
        freq = band["frequency_hz"]
        # Original fields keep their meaning: the submitted main level and
        # the A-weighting correction; the weighted level and energy are
        # those of the corrected band that feeds the total.
        assert band["level_db"] == float(MAIN[freq])
        assert band["a_weight_db"] == float(A_WEIGHTS_DB[freq])
        assert band["background_db"] == float(BACKGROUND[freq])
        assert band["corrected_level_db"] == pytest.approx(corrected[freq], rel=1e-9)
        assert band["weighted_level_db"] == pytest.approx(
            float(weighted[freq]), rel=1e-9
        )
        assert band["energy"] == pytest.approx(
            10.0 ** (float(weighted[freq]) / 10.0), rel=1e-9
        )
    # Energy contributions arrive in non-increasing order.
    energies = [b["energy"] for b in body["bands"]]
    assert energies == sorted(energies, reverse=True)


def test_verdict_uses_corrected_total_not_raw(client):
    corrected_total = expected_total_db(corrected_levels(MAIN, BACKGROUND))
    raw_total = expected_total_db(MAIN)
    below = math.floor(corrected_total * 100) / 100
    above = below + 0.01
    assert below < corrected_total < above  # sanity: not on a centi-dB boundary
    assert below < raw_total  # the raw measurement alone would exceed `below`

    low = post_assessment(client, make_csv(MAIN), f"{below:.2f}", make_csv(BACKGROUND))
    high = post_assessment(client, make_csv(MAIN), f"{above:.2f}", make_csv(BACKGROUND))
    assert low.json()["verdict"] == "NON_COMPLIANT"
    assert high.json()["verdict"] == "COMPLIANT"
    # A limit between the corrected and raw totals adjudicates the speaker,
    # not the raw measurement: raw would be NON_COMPLIANT at `above` too.
    assert raw_total > above
    assert high.json()["total_db"] != round(raw_total, 2)


def test_background_rows_shuffled_still_matched_by_frequency(client):
    shuffled = make_csv(
        BACKGROUND, newline="\n", order=[8000, 63, 1000, 500, 250, 2000, 4000, 125]
    )
    canonical = post_assessment(client, make_csv(MAIN), "140", make_csv(BACKGROUND))
    shuffled_response = post_assessment(client, make_csv(MAIN), "140", shuffled)
    assert shuffled_response.status_code == 200
    assert shuffled_response.json() == canonical.json()


@pytest.mark.parametrize(
    "background_level",
    ["88", "88.0", "95"],  # equal-energy and louder-than-measurement cases
    ids=["equal", "equal-with-decimals", "louder"],
)
def test_single_band_background_not_lower_rejects_whole_request(
    client, background_level
):
    background = dict(BACKGROUND)
    background[500] = background_level  # main measurement at 500 Hz is 88
    response = post_assessment(client, make_csv(MAIN), "140", make_csv(background))

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "BACKGROUND_NOT_LOWER"
    assert body["error"]["message"]
    assert body["error"]["details"]["bands"] == [
        {
            "frequency_hz": 500,
            "level_db": float(MAIN[500]),
            "background_db": float(background_level),
        }
    ]


def test_background_not_lower_lists_every_offending_band(client):
    background = dict(BACKGROUND)
    background[500] = "88"  # equal to the measurement
    background[2000] = "90"  # louder than the measurement (86)
    response = post_assessment(client, make_csv(MAIN), "140", make_csv(background))

    assert response.status_code == 422
    bands = response.json()["error"]["details"]["bands"]
    assert bands == [
        {"frequency_hz": 500, "level_db": 88.0, "background_db": 88.0},
        {"frequency_hz": 2000, "level_db": 86.0, "background_db": 90.0},
    ]


def test_omitted_background_file_response_unchanged(client):
    response = post_assessment(client, make_csv(MAIN), "140")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"total_db", "limit_db", "verdict", "bands"}
    assert abs(body["total_db"] - expected_total_db(MAIN)) <= 0.005 + 1e-9
    for band in body["bands"]:
        # No background was uploaded: the new fields must not appear at all.
        assert set(band) == {
            "frequency_hz",
            "level_db",
            "a_weight_db",
            "weighted_level_db",
            "energy",
        }


@pytest.mark.parametrize(
    "payload,code",
    [
        (make_csv(BACKGROUND, header="Frequency_Hz,level_db"), "INVALID_HEADER"),
        (b"frequency_hz,level_db\r\n63,\xff\xfe\r\n", "INVALID_ENCODING"),
        (
            make_csv(
                {f: BACKGROUND[f] for f in FREQUENCIES_HZ[:-1]},
                order=list(FREQUENCIES_HZ[:-1]),
            ),
            "INVALID_ROW_COUNT",
        ),
        (
            make_csv({**BACKGROUND, 250: "abc"}),
            "INVALID_LEVEL",
        ),
        (
            make_csv(BACKGROUND, order=list(FREQUENCIES_HZ[:-1]) + [63]),
            "DUPLICATE_FREQUENCY",
        ),
    ],
    ids=["bad-header", "bad-encoding", "seven-rows", "bad-level", "duplicate-band"],
)
def test_background_file_gets_same_whole_file_validation(client, payload, code):
    response = post_assessment(client, make_csv(MAIN), "140", payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == code
    assert set(body) == {"error"}


def test_oversized_background_file_rejected_with_413(client):
    payload = make_csv(BACKGROUND)
    payload += b"\n" * (MAX_CSV_BYTES + 1 - len(payload))
    response = post_assessment(client, make_csv(MAIN), "140", payload)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_background_file_does_not_excuse_missing_main_file(client):
    response = client.post(
        URL,
        files={"background_file": ("background.csv", make_csv(BACKGROUND), "text/csv")},
        data={"limit": "90"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MISSING_FILE"
