from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from .exceptions import ApiError, NetworkError, TimeoutError
from .types import (
    AfterResponseContext,
    BeforeRequestContext,
    Hooks,
    HttpMethod,
    HttpRequestOptions,
    RetryDecisionContext,
    RetryPolicy,
)
from .utils import append_path, build_error_message, merge_headers, parse_response_body


@dataclass(slots=True)
class HttpClient:
    base_url: str
    client: httpx.Client | Any | None = None
    timeout_seconds: float | None = None
    default_headers: Mapping[str, str] | None = None
    retry: RetryPolicy | None = None
    hooks: Hooks | None = None
    _owns_client: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client()
            self._owns_client = True

    def request(self, options: HttpRequestOptions) -> object:
        url = append_path(self.base_url, options.path)
        method = options.method
        retry_policy = self._resolve_retry_policy(options.retry)
        max_attempts = retry_policy.max_attempts if retry_policy else 1
        timeout_seconds = (
            options.timeout_seconds if options.timeout_seconds is not None else self.timeout_seconds
        )

        for attempt in range(1, max_attempts + 1):
            headers = merge_headers(self.default_headers, options.headers)
            context = BeforeRequestContext(
                url=url,
                path=options.path,
                method=method,
                headers=headers,
                body=options.body,
                attempt=attempt,
            )
            self._run_before_request_hooks(context)

            try:
                response = self._perform_request(
                    method=method,
                    url=url,
                    headers=context.headers,
                    query=options.query,
                    body=context.body,
                    timeout_seconds=timeout_seconds,
                )
            except httpx.TimeoutException as error:
                wrapped = TimeoutError(f"Request timed out for {url}", details={"error": error})
                self._run_error_hooks(context, wrapped)
                if self._should_retry(
                    retry_policy,
                    RetryDecisionContext(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        method=method,
                        url=url,
                        error=wrapped,
                    ),
                ):
                    self._sleep_before_retry(retry_policy, attempt)
                    continue
                raise wrapped from error
            except httpx.RequestError as error:
                wrapped = NetworkError(f"Request failed for {url}", details={"error": error})
                self._run_error_hooks(context, wrapped)
                if self._should_retry(
                    retry_policy,
                    RetryDecisionContext(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        method=method,
                        url=url,
                        error=wrapped,
                    ),
                ):
                    self._sleep_before_retry(retry_policy, attempt)
                    continue
                raise wrapped from error

            response_body = parse_response_body(response)
            after_context = AfterResponseContext(
                url=context.url,
                path=context.path,
                method=context.method,
                headers=context.headers,
                body=context.body,
                attempt=context.attempt,
                response=response,
                response_body=response_body,
            )
            self._run_after_response_hooks(after_context)

            if 200 <= response.status_code < 300:
                return response_body

            error = ApiError(
                build_error_message(response.status_code, response_body),
                status_code=response.status_code,
                response_body=response_body,
            )
            self._run_error_hooks(context, error, response=response, response_body=response_body)
            if self._should_retry(
                retry_policy,
                RetryDecisionContext(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    method=method,
                    url=url,
                    status=response.status_code,
                    error=error,
                ),
            ):
                self._sleep_before_retry(retry_policy, attempt)
                continue

            raise error

        raise RuntimeError("unreachable retry state")

    def _perform_request(
        self,
        *,
        method: HttpMethod,
        url: str,
        headers: Mapping[str, str],
        query: Mapping[str, str | int | float | bool | None] | None,
        body: object,
        timeout_seconds: float | None,
    ) -> Any:
        request_kwargs = _build_request_kwargs(
            method=method,
            url=url,
            headers=headers,
            query=query,
            body=body,
            timeout_seconds=timeout_seconds,
        )
        return self.client.request(**request_kwargs)

    def _resolve_retry_policy(self, override: RetryPolicy | bool | None) -> RetryPolicy | None:
        return _resolve_retry_policy(self.retry, override)

    def _should_retry(
        self,
        retry_policy: RetryPolicy | None,
        context: RetryDecisionContext,
    ) -> bool:
        return _should_retry(retry_policy, context)

    def _sleep_before_retry(self, retry_policy: RetryPolicy | None, attempt: int) -> None:
        delay = _calculate_retry_delay(retry_policy, attempt)
        if delay > 0:
            time.sleep(delay)

    def _run_before_request_hooks(self, context: BeforeRequestContext) -> None:
        for hook in _normalize_hook_sequence(self.hooks.before_request if self.hooks else None):
            hook(context)

    def _run_after_response_hooks(self, context: AfterResponseContext) -> None:
        for hook in _normalize_hook_sequence(self.hooks.after_response if self.hooks else None):
            hook(context)

    def _run_error_hooks(
        self,
        context: BeforeRequestContext,
        error: Exception,
        *,
        response: object | None = None,
        response_body: object | None = None,
    ) -> None:
        from .types import ErrorContext

        error_context = ErrorContext(
            url=context.url,
            path=context.path,
            method=context.method,
            headers=context.headers,
            body=context.body,
            attempt=context.attempt,
            error=error,
            response=response,
            response_body=response_body,
        )
        for hook in _normalize_hook_sequence(self.hooks.on_error if self.hooks else None):
            hook(error_context)

    def close(self) -> None:
        if self._owns_client and self.client is not None:
            self.client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


@dataclass(slots=True)
class AsyncHttpClient:
    base_url: str
    client: httpx.AsyncClient | Any | None = None
    timeout_seconds: float | None = None
    default_headers: Mapping[str, str] | None = None
    retry: RetryPolicy | None = None
    hooks: Hooks | None = None
    _owns_client: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.AsyncClient()
            self._owns_client = True

    async def request(self, options: HttpRequestOptions) -> object:
        url = append_path(self.base_url, options.path)
        method = options.method
        retry_policy = self._resolve_retry_policy(options.retry)
        max_attempts = retry_policy.max_attempts if retry_policy else 1
        timeout_seconds = (
            options.timeout_seconds if options.timeout_seconds is not None else self.timeout_seconds
        )

        for attempt in range(1, max_attempts + 1):
            headers = merge_headers(self.default_headers, options.headers)
            context = BeforeRequestContext(
                url=url,
                path=options.path,
                method=method,
                headers=headers,
                body=options.body,
                attempt=attempt,
            )
            self._run_before_request_hooks(context)

            try:
                response = await self._perform_request(
                    method=method,
                    url=url,
                    headers=context.headers,
                    query=options.query,
                    body=context.body,
                    timeout_seconds=timeout_seconds,
                )
            except httpx.TimeoutException as error:
                wrapped = TimeoutError(f"Request timed out for {url}", details={"error": error})
                self._run_error_hooks(context, wrapped)
                if self._should_retry(
                    retry_policy,
                    RetryDecisionContext(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        method=method,
                        url=url,
                        error=wrapped,
                    ),
                ):
                    await self._sleep_before_retry(retry_policy, attempt)
                    continue
                raise wrapped from error
            except httpx.RequestError as error:
                wrapped = NetworkError(f"Request failed for {url}", details={"error": error})
                self._run_error_hooks(context, wrapped)
                if self._should_retry(
                    retry_policy,
                    RetryDecisionContext(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        method=method,
                        url=url,
                        error=wrapped,
                    ),
                ):
                    await self._sleep_before_retry(retry_policy, attempt)
                    continue
                raise wrapped from error

            response_body = parse_response_body(response)
            after_context = AfterResponseContext(
                url=context.url,
                path=context.path,
                method=context.method,
                headers=context.headers,
                body=context.body,
                attempt=context.attempt,
                response=response,
                response_body=response_body,
            )
            self._run_after_response_hooks(after_context)

            if 200 <= response.status_code < 300:
                return response_body

            error = ApiError(
                build_error_message(response.status_code, response_body),
                status_code=response.status_code,
                response_body=response_body,
            )
            self._run_error_hooks(context, error, response=response, response_body=response_body)
            if self._should_retry(
                retry_policy,
                RetryDecisionContext(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    method=method,
                    url=url,
                    status=response.status_code,
                    error=error,
                ),
            ):
                await self._sleep_before_retry(retry_policy, attempt)
                continue

            raise error

        raise RuntimeError("unreachable retry state")

    async def _perform_request(
        self,
        *,
        method: HttpMethod,
        url: str,
        headers: Mapping[str, str],
        query: Mapping[str, str | int | float | bool | None] | None,
        body: object,
        timeout_seconds: float | None,
    ) -> Any:
        request_kwargs = _build_request_kwargs(
            method=method,
            url=url,
            headers=headers,
            query=query,
            body=body,
            timeout_seconds=timeout_seconds,
        )
        return await self.client.request(**request_kwargs)

    def _resolve_retry_policy(self, override: RetryPolicy | bool | None) -> RetryPolicy | None:
        return _resolve_retry_policy(self.retry, override)

    def _should_retry(
        self,
        retry_policy: RetryPolicy | None,
        context: RetryDecisionContext,
    ) -> bool:
        return _should_retry(retry_policy, context)

    async def _sleep_before_retry(self, retry_policy: RetryPolicy | None, attempt: int) -> None:
        delay = _calculate_retry_delay(retry_policy, attempt)
        if delay > 0:
            await asyncio.sleep(delay)

    def _run_before_request_hooks(self, context: BeforeRequestContext) -> None:
        for hook in _normalize_hook_sequence(self.hooks.before_request if self.hooks else None):
            hook(context)

    def _run_after_response_hooks(self, context: AfterResponseContext) -> None:
        for hook in _normalize_hook_sequence(self.hooks.after_response if self.hooks else None):
            hook(context)

    def _run_error_hooks(
        self,
        context: BeforeRequestContext,
        error: Exception,
        *,
        response: object | None = None,
        response_body: object | None = None,
    ) -> None:
        from .types import ErrorContext

        error_context = ErrorContext(
            url=context.url,
            path=context.path,
            method=context.method,
            headers=context.headers,
            body=context.body,
            attempt=context.attempt,
            error=error,
            response=response,
            response_body=response_body,
        )
        for hook in _normalize_hook_sequence(self.hooks.on_error if self.hooks else None):
            hook(error_context)

    async def aclose(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def __aenter__(self) -> AsyncHttpClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _build_request_kwargs(
    *,
    method: HttpMethod,
    url: str,
    headers: Mapping[str, str],
    query: Mapping[str, str | int | float | bool | None] | None,
    body: object,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    params = {key: value for key, value in (query or {}).items() if value is not None}
    request_kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "params": params or None,
        "timeout": timeout_seconds,
    }

    if body is not None:
        if isinstance(body, (str, bytes, bytearray)):
            request_kwargs["content"] = body
            if "content-type" not in {key.lower() for key in headers}:
                request_kwargs["headers"] = merge_headers(
                    headers,
                    {"content-type": "text/plain;charset=UTF-8"},
                )
        else:
            request_kwargs["json"] = body
            if "content-type" not in {key.lower() for key in headers}:
                request_kwargs["headers"] = merge_headers(
                    headers,
                    {"content-type": "application/json"},
                )

    return request_kwargs


def _resolve_retry_policy(
    default: RetryPolicy | None,
    override: RetryPolicy | bool | None,
) -> RetryPolicy | None:
    if override is False:
        return None

    if override is None:
        return default

    if default is None:
        return override

    return RetryPolicy(
        max_attempts=override.max_attempts,
        retry_methods=override.retry_methods or default.retry_methods,
        retry_on_statuses=override.retry_on_statuses or default.retry_on_statuses,
        retry_on_network_error=override.retry_on_network_error,
        base_delay_seconds=override.base_delay_seconds,
        max_delay_seconds=override.max_delay_seconds,
        backoff_multiplier=override.backoff_multiplier,
        should_retry=override.should_retry or default.should_retry,
    )


def _should_retry(
    retry_policy: RetryPolicy | None,
    context: RetryDecisionContext,
) -> bool:
    if retry_policy is None or context.attempt >= context.max_attempts:
        return False

    if retry_policy.retry_methods and context.method not in retry_policy.retry_methods:
        return False

    if context.status is not None and context.status not in retry_policy.retry_on_statuses:
        return False
    if (
        context.status is None
        and context.error is not None
        and not retry_policy.retry_on_network_error
    ):
        return False

    if retry_policy.should_retry is not None:
        return retry_policy.should_retry(context)

    return True


def _calculate_retry_delay(retry_policy: RetryPolicy | None, attempt: int) -> float:
    if retry_policy is None:
        return 0.0

    delay = retry_policy.base_delay_seconds * (
        retry_policy.backoff_multiplier ** max(0, attempt - 1)
    )
    return min(delay, retry_policy.max_delay_seconds)


def _normalize_hook_sequence(
    value: Callable[[Any], None] | Sequence[Callable[[Any], None]] | None,
) -> list[Callable[[Any], None]]:
    if value is None:
        return []

    if callable(value):
        return [value]

    return list(value)
