from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


def make_json_response(
    status_code: int,
    payload: Any = None,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers or {"content-type": "application/json"},
    )


def make_text_response(
    status_code: int,
    text: str = "",
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        text=text,
        headers=headers or {"content-type": "text/plain"},
    )


def make_timeout_error(url: str = "https://example.com/test") -> httpx.ReadTimeout:
    return httpx.ReadTimeout("slow", request=httpx.Request("GET", url))


def make_network_error(url: str = "https://example.com/test") -> httpx.ConnectError:
    return httpx.ConnectError("boom", request=httpx.Request("GET", url))


@dataclass(slots=True)
class FakeSyncClient:
    responses: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake responses left.")
        next_response = self.responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class FakeAsyncClient:
    responses: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake responses left.")
        next_response = self.responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response

    async def aclose(self) -> None:
        self.closed = True
