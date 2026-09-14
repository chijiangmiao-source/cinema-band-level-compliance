"""FastAPI entrypoint for the cinema sound-level assessment service."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .csv_parser import MAX_CSV_BYTES, parse_csv_bytes
from .errors import ApiError
from .models import AssessmentResponse, ErrorResponse
from .service import assess
from .validation import parse_limit

app = FastAPI(
    title="Cinema Sound Level Assessment",
    version="1.0.0",
    summary="Adjudicate octave-band sound levels against an allowed total.",
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {"loc": list(e.get("loc", ())), "type": e.get("type"), "msg": e.get("msg")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "Malformed request; expected multipart/form-data "
                "with fields 'file' and 'limit'.",
                "details": {"errors": errors},
            }
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/assessments",
    response_model=AssessmentResponse,
    responses={
        413: {"model": ErrorResponse, "description": "CSV larger than 64 KiB"},
        422: {"model": ErrorResponse, "description": "Validation failure"},
    },
)
async def create_assessment(
    file: UploadFile | None = File(
        default=None, description="UTF-8 CSV, at most 64 KiB"
    ),
    limit: str | None = Form(
        default=None,
        description="Allowed total level in dB: plain decimal, 0-140, "
        "at most two decimal places",
    ),
) -> AssessmentResponse:
    if file is None:
        raise ApiError(422, "MISSING_FILE", "Multipart field 'file' is required.")
    if limit is None:
        raise ApiError(422, "MISSING_LIMIT", "Multipart field 'limit' is required.")

    limit_db = parse_limit(limit)

    # Read at most one byte past the cap so oversized uploads are rejected
    # without buffering unbounded content.
    data = await file.read(MAX_CSV_BYTES + 1)
    levels = parse_csv_bytes(data)

    return assess(levels, limit_db)
