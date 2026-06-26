from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Literal

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


@dataclass(slots=True)
class RetryDecisionContext:
    attempt: int
    max_attempts: int
    method: HttpMethod
    url: str
    status: int | None = None
    error: object = None


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_methods: tuple[HttpMethod, ...] = ()
    retry_on_statuses: tuple[int, ...] = ()
    retry_on_network_error: bool = False
    base_delay_seconds: float = 0.0
    max_delay_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    should_retry: Callable[[RetryDecisionContext], bool] | None = None


@dataclass(slots=True)
class BeforeRequestContext:
    url: str
    path: str
    method: HttpMethod
    headers: MutableMapping[str, str]
    body: object
    attempt: int


@dataclass(slots=True)
class AfterResponseContext(BeforeRequestContext):
    response: object
    response_body: object


@dataclass(slots=True)
class ErrorContext(BeforeRequestContext):
    error: object
    response: object | None = None
    response_body: object | None = None


BeforeRequestHook = Callable[[BeforeRequestContext], None]
AfterResponseHook = Callable[[AfterResponseContext], None]
ErrorHook = Callable[[ErrorContext], None]


@dataclass(slots=True)
class Hooks:
    before_request: BeforeRequestHook | Sequence[BeforeRequestHook] | None = None
    after_response: AfterResponseHook | Sequence[AfterResponseHook] | None = None
    on_error: ErrorHook | Sequence[ErrorHook] | None = None


@dataclass(slots=True)
class RequestOptions:
    headers: Mapping[str, str] | None = None
    timeout_seconds: float | None = None
    retry: RetryPolicy | bool | None = None


@dataclass(slots=True)
class HttpRequestOptions:
    path: str
    method: HttpMethod = "GET"
    headers: Mapping[str, str] | None = None
    query: Mapping[str, str | int | float | bool | None] | None = None
    body: object = None
    form: Mapping[str, object] | None = None
    files: Mapping[str, object] | None = None
    timeout_seconds: float | None = None
    retry: RetryPolicy | bool | None = None
