"""Pydantic schemas for the assessment API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BandResult(BaseModel):
    """One octave band, listed in descending energy-contribution order."""

    frequency_hz: int
    level_db: float = Field(description="Band level L_i as submitted")
    a_weight_db: float = Field(description="A-weighting correction A_i")
    weighted_level_db: float = Field(description="L_i + A_i")
    energy: float = Field(description="Linear energy contribution 10**((L_i+A_i)/10)")
    background_db: float | None = Field(
        default=None,
        description="Background band level as submitted; present only when "
        "background_file was provided",
    )
    corrected_level_db: float | None = Field(
        default=None,
        description="Band level after subtracting the background's linear "
        "energy; present only when background_file was provided",
    )


class AssessmentResponse(BaseModel):
    total_db: float = Field(
        description="Total A-weighted level rounded half-up to 0.01 dB (display only)"
    )
    limit_db: float = Field(description="Allowed total level as submitted")
    verdict: Literal["COMPLIANT", "NON_COMPLIANT"]
    bands: list[BandResult]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
