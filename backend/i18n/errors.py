"""Typed errors with stable machine-readable codes."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        params: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=error_code, headers=headers)
        self.error_code = error_code
        self.params = params or {}


class DomainError(Exception):
    def __init__(self, error_code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.params = params or {}
