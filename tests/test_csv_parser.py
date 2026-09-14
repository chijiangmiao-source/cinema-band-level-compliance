"""Whole-file CSV validation: size, encoding, header, bands, values."""

from decimal import Decimal

import pytest

from app.csv_parser import MAX_CSV_BYTES, parse_csv_bytes
from app.errors import ApiError

CANONICAL_ROWS = [
    (63, "80"),
    (125, "78.5"),
    (250, "85"),
    (500, "88"),
    (1000, "90"),
    (2000, "86"),
    (4000, "82"),
    (8000, "75"),
]


def build_csv(rows=CANONICAL_ROWS, header="frequency_hz,level_db", newline="\r\n"):
    lines = [header] + [f"{f},{lvl}" for f, lvl in rows]
    return (newline.join(lines) + newline).encode("utf-8")


def error_code(data: bytes) -> str:
    with pytest.raises(ApiError) as exc_info:
        parse_csv_bytes(data)
    return exc_info.value.code


def test_valid_csv_parses_all_bands():
    levels = parse_csv_bytes(build_csv())
    assert levels == {f: Decimal(lvl) for f, lvl in CANONICAL_ROWS}


def test_lf_newlines_and_any_row_order_accepted():
    rows = list(reversed(CANONICAL_ROWS))
    levels = parse_csv_bytes(build_csv(rows=rows, newline="\n"))
    assert levels[1000] == Decimal("90")


def test_fractional_frequency_notation_accepted():
    rows = [("63.0", "80")] + CANONICAL_ROWS[1:]
    assert parse_csv_bytes(build_csv(rows=rows))[63] == Decimal("80")


def test_size_limit_is_64_kib_and_inclusive():
    assert MAX_CSV_BYTES == 64 * 1024
    base = build_csv()
    extra = MAX_CSV_BYTES - len(base)
    # Pad the last level with a fractional part of zeros: still a finite
    # plain decimal in range, so the file stays fully valid at exactly 64 KiB.
    rows = CANONICAL_ROWS[:-1] + [(8000, "75." + "0" * (extra - 1))]
    padded = build_csv(rows=rows)
    assert len(padded) == MAX_CSV_BYTES
    assert parse_csv_bytes(padded)[8000] == Decimal("75")


def test_one_byte_over_limit_rejected_with_413():
    extra = MAX_CSV_BYTES - len(build_csv())
    rows = CANONICAL_ROWS[:-1] + [(8000, "75." + "0" * extra)]  # one byte too many
    payload = build_csv(rows=rows)
    assert len(payload) == MAX_CSV_BYTES + 1
    with pytest.raises(ApiError) as exc_info:
        parse_csv_bytes(payload)
    assert exc_info.value.code == "FILE_TOO_LARGE"
    assert exc_info.value.status_code == 413


@pytest.mark.parametrize(
    "data",
    [
        b"\r\n" + build_csv(),  # blank first line (CRLF)
        b"\n" + build_csv(),  # blank first line (LF)
        b"\n",  # a single blank line and nothing else
    ],
    ids=["blank-first-line-crlf", "blank-first-line-lf", "single-blank-line"],
)
def test_blank_first_line_rejected(data):
    assert error_code(data) == "INVALID_HEADER"


def test_blank_line_among_data_rejected():
    lines = build_csv().split(b"\r\n")
    data = b"\r\n".join(lines[:4] + [b""] + lines[4:])  # 9 rows after header
    assert error_code(data) == "INVALID_ROW_COUNT"


def test_blank_line_replacing_data_row_rejected():
    lines = build_csv().split(b"\r\n")  # [header, 8 data rows, trailing ""]
    data = b"\r\n".join(lines[:5] + [b""] + lines[6:])  # 8 rows, one blank
    assert error_code(data) == "INVALID_FIELD_COUNT"


def test_trailing_blank_line_rejected():
    assert error_code(build_csv() + b"\r\n") == "INVALID_ROW_COUNT"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\n\n\n",
        build_csv(header="Frequency_Hz,level_db"),
        build_csv(header="frequency_hz, level_db"),
        build_csv(header="frequency_hz;level_db"),
        build_csv(header="frequency_hz,level_db,extra"),
        b"\xef\xbb\xbf" + build_csv(),  # UTF-8 BOM breaks the exact header
    ],
    ids=[
        "empty",
        "blank-lines-only",
        "capitalised",
        "space-after-comma",
        "semicolon",
        "extra-column",
        "utf8-bom",
    ],
)
def test_invalid_header_rejected(data):
    assert error_code(data) == "INVALID_HEADER"


@pytest.mark.parametrize(
    "data",
    [
        b"frequency_hz,level_db\n63,\xff\xfe\n",
        "frequency_hz,level_db\n63,80\n125,78\n250,85\n500,88\n1000,90\n"
        "2000,86\n4000,82\n8000,é\n".encode("latin-1"),
    ],
    ids=["bad-bytes", "latin1"],
)
def test_non_utf8_rejected(data):
    assert error_code(data) == "INVALID_ENCODING"


@pytest.mark.parametrize(
    "rows",
    [
        CANONICAL_ROWS[:-1],  # 7 rows
        CANONICAL_ROWS[:1],  # 1 row
        CANONICAL_ROWS + [(16000, "70")],  # 9 rows
        [],
    ],
    ids=["seven-rows", "one-row", "nine-rows", "no-rows"],
)
def test_wrong_row_count_rejected(rows):
    assert error_code(build_csv(rows=rows)) == "INVALID_ROW_COUNT"


def test_duplicate_frequency_rejected():
    rows = CANONICAL_ROWS[:-1] + [(63, "81")]  # 63 twice, 8000 missing
    assert error_code(build_csv(rows=rows)) == "DUPLICATE_FREQUENCY"


def test_duplicate_via_equivalent_notation_rejected():
    rows = [("63.0", "80"), ("63", "81")] + CANONICAL_ROWS[1:-1]
    assert error_code(build_csv(rows=rows)) == "DUPLICATE_FREQUENCY"


def test_missing_frequency_rejected():
    rows = [(16000, "70")] + CANONICAL_ROWS[1:]  # 63 swapped for unknown 16000
    # 16000 is caught first as an unknown band
    assert error_code(build_csv(rows=rows)) == "UNKNOWN_FREQUENCY"


@pytest.mark.parametrize("bad_freq", ["63.5", "100", "16000", "0"])
def test_unknown_frequency_rejected(bad_freq):
    rows = [(bad_freq, "80")] + CANONICAL_ROWS[1:]
    assert error_code(build_csv(rows=rows)) == "UNKNOWN_FREQUENCY"


@pytest.mark.parametrize("bad_freq", ["abc", "63Hz", "-63", "+63", "6_3", " 63", ""])
def test_malformed_frequency_rejected(bad_freq):
    rows = [(bad_freq, "80")] + CANONICAL_ROWS[1:]
    assert error_code(build_csv(rows=rows)) == "INVALID_FREQUENCY"


@pytest.mark.parametrize(
    "bad_level",
    [
        "abc",
        "nan",
        "NaN",
        "inf",
        "-inf",
        "1e2",
        "0x50",
        "1_0",
        "-1",
        "+80",
        "140.01",
        " 80",
        "80 ",
        ".5",
        "80.",
        "",
    ],
)
def test_invalid_level_rejected(bad_level):
    rows = [(63, bad_level)] + CANONICAL_ROWS[1:]
    assert error_code(build_csv(rows=rows)) == "INVALID_LEVEL"


@pytest.mark.parametrize("good_level", ["0", "0.00", "80", "80.5", "99.999", "140", "140.00"])
def test_boundary_levels_accepted(good_level):
    rows = [(63, good_level)] + CANONICAL_ROWS[1:]
    assert parse_csv_bytes(build_csv(rows=rows))[63] == Decimal(good_level)


@pytest.mark.parametrize(
    "row,line",
    [
        ("63,80,extra", "three-fields"),
        ("63", "one-field"),
        (",", "two-empty-fields"),
    ],
)
def test_wrong_field_count_rejected(row, line):
    rows = [row] + [f"{f},{lvl}" for f, lvl in CANONICAL_ROWS[1:]]
    data = ("frequency_hz,level_db\r\n" + "\r\n".join(rows) + "\r\n").encode()
    expected = "INVALID_FREQUENCY" if line == "two-empty-fields" else "INVALID_FIELD_COUNT"
    assert error_code(data) == expected
