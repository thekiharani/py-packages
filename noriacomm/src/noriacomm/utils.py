from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def trim_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def append_path(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path

    base = trim_trailing_slash(base_url)
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized}"


def parse_response_body(response: Any) -> object:
    content_type = str(response.headers.get("content-type", ""))

    if "application/json" in content_type:
        return response.json()

    text = getattr(response, "text", "")
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def to_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    return {}


def build_error_message(status_code: int, response_body: object) -> str:
    payload = to_object(response_body)
    for key in ("errorMessage", "detail", "message", "ErrorDescription"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    return f"Request failed with status {status_code}"


def merge_headers(*header_sets: Mapping[str, str] | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    for header_set in header_sets:
        if header_set:
            merged.update(header_set)
    return merged


def coerce_string(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def first_text(*values: object) -> str | None:
    for value in values:
        text = coerce_string(value)
        if text is not None:
            return text
    return None


def format_schedule_time(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")

    text = coerce_string(value)
    if text is None:
        raise ValueError("schedule_at must not be empty.")
    return text


def parse_decimal_from_text(value: str | None) -> Decimal | None:
    text = coerce_string(value)
    if text is None:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if match is None:
        return None

    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def normalize_query_mapping(payload: Mapping[str, object]) -> dict[str, str | None]:
    normalized: dict[str, str | None] = {}
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            normalized[key] = coerce_string(value[0] if value else None)
        else:
            normalized[key] = coerce_string(value)
    return normalized
