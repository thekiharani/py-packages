from __future__ import annotations

from typing import Any


class StorageError(Exception):
    """Wrapped storage operation failure with normalized metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        operation: str,
        provider: str,
        bucket: str | None = None,
        key: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.operation = operation
        self.provider = provider
        self.bucket = bucket
        self.key = key
        self.status_code = status_code
        self.retryable = retryable
        self.details = details
        self.cause = cause

    def __str__(self) -> str:
        return str(self.args[0])
