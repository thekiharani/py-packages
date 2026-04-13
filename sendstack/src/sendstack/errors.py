from __future__ import annotations

from typing import Any


class MailerError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        details: object = None,
        response_body: object = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = details
        self.response_body = response_body


def is_error_envelope(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("ok") is not False:
        return False
    return isinstance(value.get("error"), dict)


def is_success_envelope(value: object) -> bool:
    return isinstance(value, dict) and value.get("ok") is True and "data" in value


def error_envelope_message(value: object) -> tuple[str | None, str | None, Any]:
    if is_error_envelope(value):
        error = value["error"]
        return error.get("message"), error.get("code"), error.get("details")
    if isinstance(value, dict):
        detail = value.get("detail")
        if isinstance(detail, str) and detail.strip() != "":
            return detail, None, value.get("errors")
    return None, None, None
