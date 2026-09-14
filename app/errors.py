"""Structured API error type shared by all validation layers."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Domain error rendered as a structured JSON error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
