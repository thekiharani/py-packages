"""Small, dependency-free helpers shared across the transport and providers."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .errors import ConfigurationError


def trim_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def append_path(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path

    base = trim_trailing_slash(base_url)
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized}"


def parse_response_body(response: Any) -> object:
    if getattr(response, "status_code", None) == 204:
        return None

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

    if isinstance(value, bool):
        return "true" if value else "false"

    text = str(value).strip()
    return text or None


def first_text(*values: object) -> str | None:
    for value in values:
        text = coerce_string(value)
        if text is not None:
            return text
    return None


def require_string(value: object, field_name: str) -> str:
    normalized = coerce_string(value)

    if normalized is None:
        raise ConfigurationError(f"{field_name} is required.")

    return normalized


def compact_record(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: entry for key, entry in value.items() if entry is not None}


def coerce_boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value

    normalized = coerce_string(value)
    if normalized is None:
        return None

    lowered = normalized.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False

    return None


def coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value

    normalized = coerce_string(value)
    if normalized is None:
        return None

    match = re.match(r"-?\d+", normalized)
    if match is None:
        return None

    try:
        return int(match.group(0))
    except ValueError:
        return None


def coerce_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None

    normalized = coerce_string(value)
    if normalized is None:
        return None

    try:
        parsed = float(normalized)
    except ValueError:
        return None

    return parsed if math.isfinite(parsed) else None


def format_schedule_time(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")

    text = coerce_string(value)
    if text is None:
        raise ConfigurationError("schedule_at is required.")
    return text


def parse_number_from_text(value: str | None) -> float | None:
    text = coerce_string(value)
    if text is None:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if match is None:
        return None

    return coerce_number(match.group(0))


def normalize_query_mapping(payload: Mapping[str, object]) -> dict[str, str | None]:
    normalized: dict[str, str | None] = {}
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            normalized[key] = coerce_string(value[0] if value else None)
        else:
            normalized[key] = coerce_string(value)
    return normalized
