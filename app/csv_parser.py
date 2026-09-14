"""Strict parsing and validation of the uploaded octave-band CSV.

Every rule failure rejects the whole file with a structured :class:`ApiError`;
there is no partial acceptance.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal

from .acoustics import FREQUENCIES_HZ
from .errors import ApiError

MAX_CSV_BYTES = 64 * 1024  # 64 KiB hard cap on the uploaded CSV part
EXPECTED_HEADER = ["frequency_hz", "level_db"]
EXPECTED_FREQUENCIES = frozenset(FREQUENCIES_HZ)
MIN_LEVEL_DB = Decimal("0")
MAX_LEVEL_DB = Decimal("140")

# Plain non-negative decimal notation only: no signs, exponents, underscores,
# NaN or infinities. ASCII digits, so full-width digits are rejected too.
_DECIMAL_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def parse_csv_bytes(data: bytes) -> dict[int, Decimal]:
    """Validate the whole CSV and return {frequency_hz: level_db}."""
    if len(data) > MAX_CSV_BYTES:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            f"CSV exceeds the 64 KiB limit ({MAX_CSV_BYTES} bytes).",
            {"max_bytes": MAX_CSV_BYTES, "actual_bytes": len(data)},
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError(
            422,
            "INVALID_ENCODING",
            "CSV must be UTF-8 encoded.",
            {"offset": exc.start},
        ) from exc

    # Blank physical lines carry no data and are ignored; every other row must
    # conform exactly.
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if not rows:
        raise ApiError(
            422,
            "INVALID_HEADER",
            "CSV is empty; the first line must be exactly 'frequency_hz,level_db'.",
        )

    header, data_rows = rows[0], rows[1:]
    if header != EXPECTED_HEADER:
        raise ApiError(
            422,
            "INVALID_HEADER",
            "First line must be exactly 'frequency_hz,level_db'.",
            {"expected": EXPECTED_HEADER, "actual": header},
        )

    if len(data_rows) != len(FREQUENCIES_HZ):
        raise ApiError(
            422,
            "INVALID_ROW_COUNT",
            f"Expected exactly {len(FREQUENCIES_HZ)} data rows "
            f"(one per octave band), got {len(data_rows)}.",
            {"expected": len(FREQUENCIES_HZ), "actual": len(data_rows)},
        )

    levels: dict[int, Decimal] = {}
    for record_no, row in enumerate(data_rows, start=2):  # header is record 1
        if len(row) != 2:
            raise ApiError(
                422,
                "INVALID_FIELD_COUNT",
                f"Record {record_no} must have exactly 2 fields.",
                {"record": record_no, "fields": len(row)},
            )
        frequency = _parse_frequency(row[0], record_no)
        level = _parse_level(row[1], record_no)
        if frequency in levels:
            raise ApiError(
                422,
                "DUPLICATE_FREQUENCY",
                f"Frequency {frequency} Hz appears more than once.",
                {"record": record_no, "frequency_hz": frequency},
            )
        levels[frequency] = level

    missing = sorted(EXPECTED_FREQUENCIES - levels.keys())
    if missing:
        raise ApiError(
            422,
            "MISSING_FREQUENCY",
            "Each required octave band must appear exactly once.",
            {"missing_hz": missing},
        )
    return levels


def _parse_frequency(raw: str, record_no: int) -> int:
    if not _DECIMAL_RE.fullmatch(raw):
        raise ApiError(
            422,
            "INVALID_FREQUENCY",
            f"Record {record_no}: frequency_hz must be a plain non-negative decimal.",
            {"record": record_no, "value": raw},
        )
    value = float(raw)
    if value not in EXPECTED_FREQUENCIES:
        raise ApiError(
            422,
            "UNKNOWN_FREQUENCY",
            f"Record {record_no}: {raw} Hz is not one of the required octave bands.",
            {
                "record": record_no,
                "value": raw,
                "allowed_hz": sorted(EXPECTED_FREQUENCIES),
            },
        )
    return int(value)


def _parse_level(raw: str, record_no: int) -> Decimal:
    if not _DECIMAL_RE.fullmatch(raw):
        raise ApiError(
            422,
            "INVALID_LEVEL",
            f"Record {record_no}: level_db must be a finite plain decimal "
            "in [0.00, 140.00] dB.",
            {"record": record_no, "value": raw},
        )
    value = Decimal(raw)
    if not (MIN_LEVEL_DB <= value <= MAX_LEVEL_DB):
        raise ApiError(
            422,
            "INVALID_LEVEL",
            f"Record {record_no}: level_db {raw} dB is outside [0.00, 140.00] dB.",
            {"record": record_no, "value": raw},
        )
    return value
