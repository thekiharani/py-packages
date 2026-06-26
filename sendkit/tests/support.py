"""Shared test helpers: fake httpx transports and response builders."""

from __future__ import annotations

import asyncio
import json as _json
from collections.abc import Callable
from typing import Any

import httpx

Handler = Callable[[dict[str, Any]], httpx.Response]


def json_response(payload: Any, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=_json.dumps(payload),
        headers={"content-type": "application/json"},
    )


class FakeSyncClient:
    """Stands in for ``httpx.Client``; records calls and delegates to a handler."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        return self._handler(kwargs)

    def close(self) -> None:
        self.closed = True


class FakeAsyncClient:
    """Stands in for ``httpx.AsyncClient``; records calls and delegates to a handler."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        return self._handler(kwargs)

    async def aclose(self) -> None:
        self.closed = True


def run(value: Any) -> Any:
    """Resolve a coroutine (async client) or return the value (sync client)."""
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


def body_json(call: dict[str, Any]) -> Any:
    return call.get("json")


def body_form(call: dict[str, Any]) -> dict[str, Any]:
    return call.get("data") or {}


def query_params(call: dict[str, Any]) -> dict[str, Any]:
    return call.get("params") or {}
