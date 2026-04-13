from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .types import UNSET, QueryParams, QueryScalar, QueryValue


def normalize_base_url(base_url: str) -> str:
    text = base_url.strip()
    if text == "":
        raise TypeError("Mailer base_url is required.")

    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        raise TypeError("Mailer base_url must be a valid absolute URL.")

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, "")
    )


def build_request_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def serialize_datetime(value: datetime) -> str:
    if value.tzinfo is UTC:
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="milliseconds")


def serialize_query_value(value: QueryScalar) -> str:
    if isinstance(value, datetime):
        return serialize_datetime(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def merge_query_params(*parts: QueryParams | None) -> dict[str, QueryValue] | None:
    merged: dict[str, QueryValue] = {}
    for part in parts:
        if not part:
            continue
        for key, value in part.items():
            if value is not None:
                merged[key] = value
    return merged or None


def append_query_params(url: str, query: QueryParams | None) -> str:
    if not query:
        return url

    parts = urlsplit(url)
    current = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    filtered = [(key, value) for key, value in current if key not in query]
    filtered.extend(normalize_query_pairs(query))
    encoded = urlencode(filtered, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded, parts.fragment))


def normalize_query_pairs(query: QueryParams | None) -> list[tuple[str, str]]:
    if not query:
        return []

    pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        if value is None:
            continue
        if _is_query_sequence(value):
            for item in value:
                if item is not None:
                    pairs.append((key, serialize_query_value(item)))
            continue
        pairs.append((key, serialize_query_value(value)))
    return pairs


def merge_headers(*parts: Mapping[str, str] | httpx.Headers | None) -> httpx.Headers:
    headers = httpx.Headers()
    for part in parts:
        if part:
            headers.update(part)
    return headers


def parse_response_body(response: httpx.Response, _context: object = None) -> object:
    text = response.text
    if text.strip() == "":
        return None

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def prepare_request_body(body: object, headers: httpx.Headers) -> object:
    if body is UNSET:
        return UNSET

    if is_native_body(body):
        return body

    if "content-type" not in headers:
        headers["content-type"] = "application/json"

    return json.dumps(body, separators=(",", ":"), default=json_default)


def is_native_body(body: object) -> bool:
    return isinstance(body, (str, bytes, bytearray, memoryview))


def json_default(value: object) -> object:
    if isinstance(value, datetime):
        return serialize_datetime(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def as_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _is_query_sequence(value: QueryValue) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
