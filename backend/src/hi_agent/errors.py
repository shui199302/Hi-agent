"""Structured API and runtime errors."""

from __future__ import annotations

from typing import Any


class HiAgentError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(HiAgentError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            "NOT_FOUND",
            f"{resource} 不存在",
            status_code=404,
            details={"resource": resource, "id": resource_id},
        )


class ConflictError(HiAgentError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(code, message, status_code=409, details=details)


class ServiceUnavailableError(HiAgentError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(code, message, status_code=503, details=details)
