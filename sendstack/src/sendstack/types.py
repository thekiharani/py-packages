from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeAlias

import httpx

UNSET = object()

QueryScalar: TypeAlias = str | int | float | bool | datetime
QueryItem: TypeAlias = QueryScalar | None
QueryValue: TypeAlias = QueryItem | Sequence[QueryItem]
QueryParams: TypeAlias = Mapping[str, QueryValue]


@dataclass(slots=True)
class MailerRequestContext:
    method: str
    path: str
    url: str
    headers: httpx.Headers
    body: object = UNSET
    timeout_seconds: float | None = None
    attempt: int = 1


@dataclass(slots=True)
class MailerResponseContext:
    request: MailerRequestContext
    response: httpx.Response
    payload: object


@dataclass(slots=True)
class MailerRetryContext:
    request: MailerRequestContext
    attempt: int
    response: httpx.Response | None = None
    error: object = None


AuthValueProvider = Callable[
    [MailerRequestContext],
    str | Mapping[str, str] | Awaitable[str | Mapping[str, str]],
]
ResponseParser = Callable[[httpx.Response, MailerRequestContext], object | Awaitable[object]]
ResponseTransformer = Callable[[MailerResponseContext], object | Awaitable[object]]
RetryPredicate = Callable[[MailerRetryContext], bool | Awaitable[bool]]
RetryDelay = Callable[[MailerRetryContext], float | int | Awaitable[float | int]]
MiddlewareNext = Callable[
    [MailerRequestContext],
    MailerResponseContext | Awaitable[MailerResponseContext],
]
MailerMiddleware = Callable[
    [MailerRequestContext, MiddlewareNext],
    MailerResponseContext | Awaitable[MailerResponseContext],
]


@dataclass(slots=True)
class BearerAuthStrategy:
    token: str | Callable[[MailerRequestContext], str | Awaitable[str]]
    header_name: str = "authorization"
    prefix: str = "Bearer"


@dataclass(slots=True)
class HeadersAuthStrategy:
    headers: Mapping[str, str] | Callable[
        [MailerRequestContext],
        Mapping[str, str] | Awaitable[Mapping[str, str]],
    ]


MailerAuthStrategy: TypeAlias = BearerAuthStrategy | HeadersAuthStrategy


@dataclass(slots=True)
class RetryOptions:
    max_attempts: int = 2
    delay_seconds: float | int | RetryDelay | None = None
    should_retry: RetryPredicate | None = None


@dataclass(slots=True)
class RequestOptions:
    headers: Mapping[str, str] | httpx.Headers | None = None
    query: QueryParams | None = None
    timeout_seconds: float | None = None
    authenticated: bool | None = None
    auth: MailerAuthStrategy | bool | None = None
    retry: RetryOptions | int | bool | None = None
    middleware: Sequence[MailerMiddleware] | None = None
    parse_response: ResponseParser | None = None
    transform_response: ResponseTransformer | None = None
    unwrap_data: bool | None = None
    client: Any | None = None
    idempotency_key: str | None = None
    body: object = UNSET
