from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any


def trim_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def append_path(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path

    base = trim_trailing_slash(base_url)
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized}"


def encode_basic_auth(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode()
    return base64.b64encode(raw).decode("ascii")


def to_amount_string(value: str | int | float) -> str:
    if isinstance(value, str):
        return value

    if isinstance(value, float):
        return format(value, "f").rstrip("0").rstrip(".") or "0"

    return str(value)


def build_mpesa_timestamp_value(dt: datetime | None = None) -> str:
    current = dt or datetime.now()
    return current.strftime("%Y%m%d%H%M%S")


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
    for key in ("errorMessage", "detail", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    return f"Request failed with status {status_code}"


def normalize_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    return dict(headers or {})


def merge_headers(*header_sets: Mapping[str, str] | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    for header_set in header_sets:
        if header_set:
            merged.update(header_set)
    return merged
