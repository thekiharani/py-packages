"""Error type and response-envelope helpers for the SendStack SDK.

A single ``SendstackError`` plus the predicates and the mapping function used to
turn a failed response payload into a structured error.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SendstackError(Exception):
    """Raised for any non-2xx response (or a failure that maps to one).

    Attributes:

    - ``status_code`` - the HTTP status (``0`` when the SDK gives up after
      exhausting retries without a response).
    - ``code`` - a machine-readable error code when the API supplies one.
    - ``details`` - structured validation/error details when present.
    - ``response_body`` - the parsed response payload (or raw text/error).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        details: Any = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        self.response_body = response_body


def is_error_envelope(value: object) -> bool:
    """Return ``True`` for a ``{"ok": false, "error": {...}}`` envelope."""

    return (
        isinstance(value, Mapping)
        and value.get("ok") is False
        and isinstance(value.get("error"), Mapping)
    )


def is_success_envelope(value: object) -> bool:
    """Return ``True`` for a ``{"ok": true, "data": ...}`` envelope."""

    return isinstance(value, Mapping) and value.get("ok") is True and "data" in value


def to_sendstack_error(status_code: int, payload: object) -> SendstackError:
    """Build a :class:`SendstackError` from a failed response payload.

    Branch order: error envelope first, then FastAPI-style ``{"detail": ...}``,
    then a generic ``{"message": ...}`` object, then an exception, then a bare
    string, then a status fallback.
    """

    if is_error_envelope(payload):
        error = payload["error"]  # type: ignore[index]
        message = error.get("message")
        return SendstackError(
            message if isinstance(message, str) and message != "" else _status_message(status_code),
            status_code=status_code,
            code=error.get("code"),
            details=error.get("details"),
            response_body=payload,
        )

    if isinstance(payload, Mapping):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip() != "":
            return SendstackError(
                detail,
                status_code=status_code,
                details=payload.get("errors"),
                response_body=payload,
            )

        message = payload.get("message")
        if isinstance(message, str) and message.strip() != "":
            code = payload.get("code")
            return SendstackError(
                message,
                status_code=status_code,
                code=code if isinstance(code, str) else None,
                details=payload.get("details"),
                response_body=payload,
            )

    if isinstance(payload, Exception):
        return SendstackError(str(payload), status_code=status_code, response_body=payload)

    if isinstance(payload, str) and payload.strip() != "":
        return SendstackError(payload, status_code=status_code, response_body=payload)

    return SendstackError(
        _status_message(status_code),
        status_code=status_code,
        response_body=payload,
    )


def _status_message(status_code: int) -> str:
    return f"SendStack request failed with status {status_code}."
