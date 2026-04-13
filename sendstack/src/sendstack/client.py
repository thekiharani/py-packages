from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .errors import MailerError, error_envelope_message, is_success_envelope
from .types import (
    UNSET,
    BearerAuthStrategy,
    HeadersAuthStrategy,
    MailerAuthStrategy,
    MailerMiddleware,
    MailerRequestContext,
    MailerResponseContext,
    MailerRetryContext,
    RequestOptions,
    ResponseParser,
    ResponseTransformer,
    RetryOptions,
)
from .utils import (
    append_query_params,
    as_mapping,
    build_request_url,
    merge_headers,
    merge_query_params,
    normalize_base_url,
    parse_response_body,
    prepare_request_body,
    serialize_datetime,
)

DEFAULT_TIMEOUT_SECONDS = 30.0
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class _MailerBase:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | httpx.Headers | None = None,
        query: Mapping[str, object] | None = None,
        auth: MailerAuthStrategy | bool | None = None,
        retry: RetryOptions | int | bool | None = None,
        middleware: Sequence[MailerMiddleware] | None = None,
        parse_response: ResponseParser | None = None,
        transform_response: ResponseTransformer | None = None,
    ) -> None:
        normalized_api_key = (api_key or "").strip()
        self.api_key = normalized_api_key
        self.base_url = normalize_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self._default_headers = headers
        self._default_query = query
        self._default_auth = (
            auth
            if auth is not None
            else (
                False
                if normalized_api_key == ""
                else HeadersAuthStrategy(headers={"x-api-key": normalized_api_key})
            )
        )
        self._default_retry = retry
        self._default_middleware = tuple(middleware or ())
        self._default_parse_response = parse_response
        self._default_transform_response = transform_response

    def _effective_options(self, options: RequestOptions | None) -> RequestOptions:
        return options if options is not None else RequestOptions()

    def _build_request_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        body: object,
        headers: httpx.Headers,
        timeout_seconds: float | None,
    ) -> MailerRequestContext:
        url = append_query_params(build_request_url(self.base_url, path), query)
        return MailerRequestContext(
            method=method.upper(),
            path=path,
            url=url,
            headers=headers,
            body=body,
            timeout_seconds=timeout_seconds,
            attempt=attempt,
        )

    def _select_timeout(self, options: RequestOptions) -> float | None:
        if options.timeout_seconds is not None:
            return options.timeout_seconds
        return self.timeout_seconds

    def _select_parse_response(self, options: RequestOptions) -> ResponseParser | None:
        return (
            options.parse_response
            if options.parse_response is not None
            else self._default_parse_response
        )

    def _select_transform_response(self, options: RequestOptions) -> ResponseTransformer | None:
        return (
            options.transform_response
            if options.transform_response is not None
            else self._default_transform_response
        )

    def _select_retry(self, options: RequestOptions) -> RetryOptions | int | bool | None:
        if options.retry is not None:
            return options.retry
        return self._default_retry

    def _select_middleware(self, options: RequestOptions) -> tuple[MailerMiddleware, ...]:
        return (*self._default_middleware, *(options.middleware or ()))

    def _select_query(self, options: RequestOptions) -> dict[str, object] | None:
        return merge_query_params(self._default_query, options.query)

    def _fallback_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        timeout_seconds: float | None,
    ) -> MailerRequestContext:
        query = self._select_query(options)
        headers = merge_headers(self._default_headers, options.headers)
        return self._build_request_context(
            attempt=attempt,
            method=method,
            path=path,
            options=options,
            query=query,
            body=UNSET,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )


class Mailer(_MailerBase):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str,
        client: httpx.Client | Any | None = None,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | httpx.Headers | None = None,
        query: Mapping[str, object] | None = None,
        auth: MailerAuthStrategy | bool | None = None,
        retry: RetryOptions | int | bool | None = None,
        middleware: Sequence[MailerMiddleware] | None = None,
        parse_response: ResponseParser | None = None,
        transform_response: ResponseTransformer | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            query=query,
            auth=auth,
            retry=retry,
            middleware=middleware,
            parse_response=parse_response,
            transform_response=transform_response,
        )
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self.emails = EmailOperations(self)
        self.sms = SmsOperations(self)
        self.whatsapp = WhatsAppOperations(self)
        self.merchant = MerchantOperations(self)
        self.domains = DomainOperations(self)
        self.api_keys = ApiKeyOperations(self)
        self.apiKeys = self.api_keys
        self.webhooks = WebhookOperations(self)
        self.health = HealthOperations(self)

    def request(
        self,
        method: str,
        path: str,
        options: RequestOptions | None = None,
    ) -> object:
        request_options = self._effective_options(options)
        timeout_seconds = self._select_timeout(request_options)
        parse_response = self._select_parse_response(request_options)
        transform_response = self._select_transform_response(request_options)
        retry_policy = _normalize_retry_policy(self._select_retry(request_options))
        middleware = self._select_middleware(request_options)
        query = self._select_query(request_options)

        for attempt in range(1, retry_policy.max_attempts + 1):
            client = request_options.client or self._client
            fallback_context = self._fallback_context(
                attempt=attempt,
                method=method,
                path=path,
                options=request_options,
                timeout_seconds=timeout_seconds,
            )

            try:
                context = self._build_sync_request_context(
                    attempt=attempt,
                    method=method,
                    path=path,
                    options=request_options,
                    query=query,
                    timeout_seconds=timeout_seconds,
                )

                def terminal(
                    request_context: MailerRequestContext,
                    resolved_client: Any = client,
                    resolved_parser: ResponseParser | None = parse_response,
                ) -> MailerResponseContext:
                    return _sync_transport(
                        request_context,
                        client=resolved_client,
                        parse_response=resolved_parser,
                    )

                response_context = _run_sync_middleware_stack(
                    middleware,
                    context,
                    terminal,
                )

                if (
                    not response_context.response.is_success
                    and attempt < retry_policy.max_attempts
                    and _sync_should_retry(
                        retry_policy,
                        MailerRetryContext(
                            request=response_context.request,
                            attempt=attempt,
                            response=response_context.response,
                        ),
                    )
                ):
                    _sleep_seconds(
                        _sync_retry_delay(
                            retry_policy,
                            MailerRetryContext(
                                request=response_context.request,
                                attempt=attempt,
                                response=response_context.response,
                            ),
                        )
                    )
                    continue

                return _sync_transform_response(
                    response_context,
                    transform_response,
                    unwrap_data=request_options.unwrap_data,
                )
            except Exception as error:
                if (
                    attempt < retry_policy.max_attempts
                    and _sync_should_retry(
                        retry_policy,
                        MailerRetryContext(
                            request=fallback_context,
                            attempt=attempt,
                            error=error,
                        ),
                    )
                ):
                    _sleep_seconds(
                        _sync_retry_delay(
                            retry_policy,
                            MailerRetryContext(
                                request=fallback_context,
                                attempt=attempt,
                                error=error,
                            ),
                        )
                    )
                    continue
                raise

        raise MailerError("Mailer request exhausted all retry attempts.", status_code=0)

    def _build_sync_request_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        timeout_seconds: float | None,
    ) -> MailerRequestContext:
        headers = merge_headers(self._default_headers, options.headers)
        authenticated = True if options.authenticated is None else options.authenticated
        auth = self._default_auth if options.auth is None else options.auth

        if not authenticated:
            if "authorization" in headers:
                del headers["authorization"]
        else:
            if not auth and not _has_explicit_auth_headers(headers):
                raise TypeError("Mailer auth is required for authenticated requests.")
            if auth:
                auth_headers = _resolve_sync_auth_headers(
                    auth,
                    self._build_request_context(
                        attempt=attempt,
                        method=method,
                        path=path,
                        options=options,
                        query=query,
                        body=UNSET,
                        headers=headers,
                        timeout_seconds=timeout_seconds,
                    ),
                )
                headers.update(auth_headers)

        if "accept" not in headers:
            headers["accept"] = "application/json"
        if options.idempotency_key:
            headers["idempotency-key"] = options.idempotency_key

        body = prepare_request_body(options.body, headers)
        return self._build_request_context(
            attempt=attempt,
            method=method,
            path=path,
            options=options,
            query=query,
            body=body,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Mailer:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class AsyncMailer(_MailerBase):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str,
        client: httpx.AsyncClient | Any | None = None,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | httpx.Headers | None = None,
        query: Mapping[str, object] | None = None,
        auth: MailerAuthStrategy | bool | None = None,
        retry: RetryOptions | int | bool | None = None,
        middleware: Sequence[MailerMiddleware] | None = None,
        parse_response: ResponseParser | None = None,
        transform_response: ResponseTransformer | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            query=query,
            auth=auth,
            retry=retry,
            middleware=middleware,
            parse_response=parse_response,
            transform_response=transform_response,
        )
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None
        self.emails = AsyncEmailOperations(self)
        self.sms = AsyncSmsOperations(self)
        self.whatsapp = AsyncWhatsAppOperations(self)
        self.merchant = AsyncMerchantOperations(self)
        self.domains = AsyncDomainOperations(self)
        self.api_keys = AsyncApiKeyOperations(self)
        self.apiKeys = self.api_keys
        self.webhooks = AsyncWebhookOperations(self)
        self.health = AsyncHealthOperations(self)

    async def request(
        self,
        method: str,
        path: str,
        options: RequestOptions | None = None,
    ) -> object:
        request_options = self._effective_options(options)
        timeout_seconds = self._select_timeout(request_options)
        parse_response = self._select_parse_response(request_options)
        transform_response = self._select_transform_response(request_options)
        retry_policy = _normalize_retry_policy(self._select_retry(request_options))
        middleware = self._select_middleware(request_options)
        query = self._select_query(request_options)

        for attempt in range(1, retry_policy.max_attempts + 1):
            client = request_options.client or self._client
            fallback_context = self._fallback_context(
                attempt=attempt,
                method=method,
                path=path,
                options=request_options,
                timeout_seconds=timeout_seconds,
            )

            try:
                context = await self._build_async_request_context(
                    attempt=attempt,
                    method=method,
                    path=path,
                    options=request_options,
                    query=query,
                    timeout_seconds=timeout_seconds,
                )

                async def terminal(
                    request_context: MailerRequestContext,
                    resolved_client: Any = client,
                    resolved_parser: ResponseParser | None = parse_response,
                ) -> MailerResponseContext:
                    return await _async_transport(
                        request_context,
                        client=resolved_client,
                        parse_response=resolved_parser,
                    )

                response_context = await _run_async_middleware_stack(
                    middleware,
                    context,
                    terminal,
                )

                if (
                    not response_context.response.is_success
                    and attempt < retry_policy.max_attempts
                    and await _async_should_retry(
                        retry_policy,
                        MailerRetryContext(
                            request=response_context.request,
                            attempt=attempt,
                            response=response_context.response,
                        ),
                    )
                ):
                    await _async_sleep_seconds(
                        await _async_retry_delay(
                            retry_policy,
                            MailerRetryContext(
                                request=response_context.request,
                                attempt=attempt,
                                response=response_context.response,
                            ),
                        )
                    )
                    continue

                return await _async_transform_response(
                    response_context,
                    transform_response,
                    unwrap_data=request_options.unwrap_data,
                )
            except Exception as error:
                if (
                    attempt < retry_policy.max_attempts
                    and await _async_should_retry(
                        retry_policy,
                        MailerRetryContext(
                            request=fallback_context,
                            attempt=attempt,
                            error=error,
                        ),
                    )
                ):
                    await _async_sleep_seconds(
                        await _async_retry_delay(
                            retry_policy,
                            MailerRetryContext(
                                request=fallback_context,
                                attempt=attempt,
                                error=error,
                            ),
                        )
                    )
                    continue
                raise

        raise MailerError("Mailer request exhausted all retry attempts.", status_code=0)

    async def _build_async_request_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        timeout_seconds: float | None,
    ) -> MailerRequestContext:
        headers = merge_headers(self._default_headers, options.headers)
        authenticated = True if options.authenticated is None else options.authenticated
        auth = self._default_auth if options.auth is None else options.auth

        if not authenticated:
            if "authorization" in headers:
                del headers["authorization"]
        else:
            if not auth and not _has_explicit_auth_headers(headers):
                raise TypeError("Mailer auth is required for authenticated requests.")
            if auth:
                auth_headers = await _resolve_async_auth_headers(
                    auth,
                    self._build_request_context(
                        attempt=attempt,
                        method=method,
                        path=path,
                        options=options,
                        query=query,
                        body=UNSET,
                        headers=headers,
                        timeout_seconds=timeout_seconds,
                    ),
                )
                headers.update(auth_headers)

        if "accept" not in headers:
            headers["accept"] = "application/json"
        if options.idempotency_key:
            headers["idempotency-key"] = options.idempotency_key

        body = prepare_request_body(options.body, headers)
        return self._build_request_context(
            attempt=attempt,
            method=method,
            path=path,
            options=options,
            query=query,
            body=body,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncMailer:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


class EmailOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer
        self.sendBatch = self.send_batch

    def quote(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/emails/quote",
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    def send(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/emails",
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    def send_batch(
        self,
        requests: Sequence[Mapping[str, Any]],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            "/emails/batch",
            _replace_request_options(
                options,
                body=[_normalize_send_email_request(request) for request in requests],
                transform_response=(
                    options.transform_response
                    if options and options.transform_response
                    else _extract_data_array_response
                ),
            ),
        )

    def get(self, email_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", f"/emails/{_quote(email_id)}", options)

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "status": status,
            },
            options.query if options else None,
        )
        return self._mailer.request(
            "GET",
            "/emails",
            _replace_request_options(options, query=query),
        )


class AsyncEmailOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer
        self.sendBatch = self.send_batch

    async def quote(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/emails/quote",
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    async def send(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/emails",
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    async def send_batch(
        self,
        requests: Sequence[Mapping[str, Any]],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/emails/batch",
            _replace_request_options(
                options,
                body=[_normalize_send_email_request(request) for request in requests],
                transform_response=(
                    options.transform_response
                    if options and options.transform_response
                    else _extract_data_array_response
                ),
            ),
        )

    async def get(self, email_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", f"/emails/{_quote(email_id)}", options)

    async def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "status": status,
            },
            options.query if options else None,
        )
        return await self._mailer.request(
            "GET", "/emails", _replace_request_options(options, query=query)
        )


class SmsOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def quote(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/sms/quote",
            _replace_request_options(options, body=dict(request)),
        )

    def send(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/sms",
            _replace_request_options(options, body=dict(request)),
        )

    def get(self, message_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", f"/sms/{_quote(message_id)}", options)

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "status": status,
            },
            options.query if options else None,
        )
        return self._mailer.request(
            "GET",
            "/sms",
            _replace_request_options(options, query=query),
        )


class AsyncSmsOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def quote(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/sms/quote",
            _replace_request_options(options, body=dict(request)),
        )

    async def send(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/sms",
            _replace_request_options(options, body=dict(request)),
        )

    async def get(self, message_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", f"/sms/{_quote(message_id)}", options)

    async def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "status": status,
            },
            options.query if options else None,
        )
        return await self._mailer.request(
            "GET", "/sms", _replace_request_options(options, query=query)
        )


class WhatsAppOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def quote(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/whatsapp/messages/quote",
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )

    def send(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/whatsapp/messages",
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )

    def get(self, message_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", f"/whatsapp/messages/{_quote(message_id)}", options)

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "status": status,
            },
            options.query if options else None,
        )
        return self._mailer.request(
            "GET",
            "/whatsapp/messages",
            _replace_request_options(options, query=query),
        )


class AsyncWhatsAppOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def quote(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/whatsapp/messages/quote",
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )

    async def send(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/whatsapp/messages",
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )

    async def get(self, message_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request(
            "GET",
            f"/whatsapp/messages/{_quote(message_id)}",
            options,
        )

    async def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "status": status,
            },
            options.query if options else None,
        )
        return await self._mailer.request(
            "GET",
            "/whatsapp/messages",
            _replace_request_options(options, query=query),
        )


class MerchantOperations:
    def __init__(self, mailer: Mailer) -> None:
        self.messages = MerchantMessageOperations(mailer)
        self.emails = MerchantEmailOperations(mailer)
        self.sms = MerchantSmsOperations(mailer)
        self.whatsapp = MerchantWhatsAppOperations(mailer)


class AsyncMerchantOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self.messages = AsyncMerchantMessageOperations(mailer)
        self.emails = AsyncMerchantEmailOperations(mailer)
        self.sms = AsyncMerchantSmsOperations(mailer)
        self.whatsapp = AsyncMerchantWhatsAppOperations(mailer)


class MerchantMessageOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def list(
        self,
        merchant_id: str,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        channel: str | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "channel": channel,
                "status": status,
            },
            options.query if options else None,
        )
        return self._mailer.request(
            "GET",
            _merchant_messages_path(merchant_id),
            _replace_request_options(options, query=query),
        )

    def get(
        self,
        merchant_id: str,
        message_id: str,
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "GET",
            _merchant_messages_path(merchant_id, f"/{_quote(message_id)}"),
            options,
        )


class AsyncMerchantMessageOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def list(
        self,
        merchant_id: str,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        per_page: int | None = None,
        channel: str | None = None,
        status: str | None = None,
    ) -> object:
        query = merge_query_params(
            {
                "limit": limit,
                "cursor": cursor,
                "per_page": per_page,
                "channel": channel,
                "status": status,
            },
            options.query if options else None,
        )
        return await self._mailer.request(
            "GET",
            _merchant_messages_path(merchant_id),
            _replace_request_options(options, query=query),
        )

    async def get(
        self, merchant_id: str, message_id: str, options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "GET",
            _merchant_messages_path(merchant_id, f"/{_quote(message_id)}"),
            options,
        )


class MerchantEmailOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer
        self.quoteGroup = self.quote_group
        self.sendGroup = self.send_group

    def quote(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email/quote"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    def quote_group(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email/group/quote"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    def send(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    def send_group(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email/group"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )


class AsyncMerchantEmailOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer
        self.quoteGroup = self.quote_group
        self.sendGroup = self.send_group

    async def quote(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email/quote"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    async def quote_group(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email/group/quote"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    async def send(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )

    async def send_group(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/email/group"),
            _replace_request_options(options, body=_normalize_send_email_request(request)),
        )


class MerchantSmsOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def quote(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/sms/quote"),
            _replace_request_options(options, body=dict(request)),
        )

    def send(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/sms"),
            _replace_request_options(options, body=dict(request)),
        )


class AsyncMerchantSmsOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def quote(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/sms/quote"),
            _replace_request_options(options, body=dict(request)),
        )

    async def send(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/sms"),
            _replace_request_options(options, body=dict(request)),
        )


class MerchantWhatsAppOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def quote(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/whatsapp/quote"),
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )

    def send(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/whatsapp"),
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )


class AsyncMerchantWhatsAppOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def quote(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/whatsapp/quote"),
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )

    async def send(
        self,
        merchant_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            _merchant_messages_path(merchant_id, "/whatsapp"),
            _replace_request_options(options, body=_normalize_whatsapp_request(request)),
        )


class DomainOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/domains",
            _replace_request_options(options, body=dict(request)),
        )

    def list(self, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", "/domains", options)

    def get(self, domain_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", f"/domains/{_quote(domain_id)}", options)

    def verify(self, domain_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("POST", f"/domains/{_quote(domain_id)}/verify", options)

    def remove(self, domain_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("DELETE", f"/domains/{_quote(domain_id)}", options)


class AsyncDomainOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def create(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/domains",
            _replace_request_options(options, body=dict(request)),
        )

    async def list(self, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", "/domains", options)

    async def get(self, domain_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", f"/domains/{_quote(domain_id)}", options)

    async def verify(self, domain_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("POST", f"/domains/{_quote(domain_id)}/verify", options)

    async def remove(self, domain_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("DELETE", f"/domains/{_quote(domain_id)}", options)


class ApiKeyOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def create(
        self,
        request: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> object:
        return self._mailer.request(
            "POST",
            "/api-keys",
            _replace_request_options(options, body=_serialize_create_api_key_request(request)),
        )

    def list(self, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", "/api-keys", options)

    def get(self, api_key_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", f"/api-keys/{_quote(api_key_id)}", options)

    def remove(self, api_key_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("DELETE", f"/api-keys/{_quote(api_key_id)}", options)


class AsyncApiKeyOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def create(
        self,
        request: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/api-keys",
            _replace_request_options(options, body=_serialize_create_api_key_request(request)),
        )

    async def list(self, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", "/api-keys", options)

    async def get(self, api_key_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", f"/api-keys/{_quote(api_key_id)}", options)

    async def remove(self, api_key_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("DELETE", f"/api-keys/{_quote(api_key_id)}", options)


class WebhookOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "POST",
            "/webhooks",
            _replace_request_options(options, body=dict(request)),
        )

    def list(self, options: RequestOptions | None = None) -> object:
        return self._mailer.request("GET", "/webhooks", options)

    def remove(self, webhook_id: str, options: RequestOptions | None = None) -> object:
        return self._mailer.request("DELETE", f"/webhooks/{_quote(webhook_id)}", options)


class AsyncWebhookOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def create(
        self, request: Mapping[str, Any], options: RequestOptions | None = None
    ) -> object:
        return await self._mailer.request(
            "POST",
            "/webhooks",
            _replace_request_options(options, body=dict(request)),
        )

    async def list(self, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("GET", "/webhooks", options)

    async def remove(self, webhook_id: str, options: RequestOptions | None = None) -> object:
        return await self._mailer.request("DELETE", f"/webhooks/{_quote(webhook_id)}", options)


class HealthOperations:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    def live(self, options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "GET",
            _root_url_path(self._mailer.base_url, "/livez"),
            _with_default_unauthenticated(options),
        )

    def check(self, options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "GET",
            _root_url_path(self._mailer.base_url, "/healthz"),
            _with_default_unauthenticated(options),
        )

    def ready(self, options: RequestOptions | None = None) -> object:
        return self._mailer.request(
            "GET",
            _root_url_path(self._mailer.base_url, "/readyz"),
            _with_default_unauthenticated(options),
        )


class AsyncHealthOperations:
    def __init__(self, mailer: AsyncMailer) -> None:
        self._mailer = mailer

    async def live(self, options: RequestOptions | None = None) -> object:
        return await self._mailer.request(
            "GET",
            _root_url_path(self._mailer.base_url, "/livez"),
            _with_default_unauthenticated(options),
        )

    async def check(self, options: RequestOptions | None = None) -> object:
        return await self._mailer.request(
            "GET",
            _root_url_path(self._mailer.base_url, "/healthz"),
            _with_default_unauthenticated(options),
        )

    async def ready(self, options: RequestOptions | None = None) -> object:
        return await self._mailer.request(
            "GET",
            _root_url_path(self._mailer.base_url, "/readyz"),
            _with_default_unauthenticated(options),
        )


def _with_default_unauthenticated(options: RequestOptions | None) -> RequestOptions:
    authenticated = (
        False
        if options is None or options.authenticated is None
        else options.authenticated
    )
    return _replace_request_options(options, authenticated=authenticated)


def _replace_request_options(options: RequestOptions | None, **changes: object) -> RequestOptions:
    base = options if options is not None else RequestOptions()
    return replace(base, **changes)


def _normalize_send_email_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename_alias(payload, "reply_to", "replyTo")
    _rename_alias(payload, "scheduled_at", "scheduledAt")
    _rename_alias(payload, "configuration_set_name", "configurationSetName")
    _rename_alias(payload, "tenant_name", "tenantName")
    _rename_alias(payload, "endpoint_id", "endpointId")
    _rename_alias(
        payload,
        "feedback_forwarding_email_address",
        "feedbackForwardingEmailAddress",
    )
    _rename_alias(
        payload,
        "feedback_forwarding_email_address_identity_arn",
        "feedbackForwardingEmailAddressIdentityArn",
    )
    _rename_alias(
        payload,
        "from_email_address_identity_arn",
        "fromEmailAddressIdentityArn",
    )
    _rename_alias(payload, "list_management_options", "listManagementOptions")

    list_management_options = payload.get("listManagementOptions")
    if isinstance(list_management_options, Mapping):
        payload["listManagementOptions"] = _normalize_list_management_options(
            list_management_options
        )

    attachments = payload.get("attachments")
    if isinstance(attachments, Sequence) and not isinstance(attachments, (str, bytes, bytearray)):
        payload["attachments"] = [
            _normalize_email_attachment(attachment)
            if isinstance(attachment, Mapping)
            else attachment
            for attachment in attachments
        ]
    return payload


def _serialize_create_api_key_request(request: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(request or {})
    if "expires_at" in payload and "expiresAt" not in payload:
        payload["expiresAt"] = payload.pop("expires_at")
    value = payload.get("expiresAt")
    if isinstance(value, datetime):
        payload["expiresAt"] = serialize_datetime(value)
    return payload


def _normalize_whatsapp_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename_alias(payload, "template_variables", "variables")
    return payload


def _normalize_list_management_options(options: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(options)
    _rename_alias(payload, "contact_list_name", "contactListName")
    _rename_alias(payload, "topic_name", "topicName")
    return payload


def _normalize_email_attachment(attachment: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(attachment)
    _rename_alias(payload, "content_type", "contentType")
    _rename_alias(payload, "content_id", "contentId")
    _rename_alias(payload, "content_disposition", "disposition")
    return payload


def _rename_alias(payload: dict[str, Any], snake_name: str, camel_name: str) -> None:
    if snake_name in payload and camel_name not in payload:
        payload[camel_name] = payload.pop(snake_name)


def _has_explicit_auth_headers(headers: httpx.Headers) -> bool:
    return "authorization" in headers or "x-api-key" in headers


def _merchant_messages_path(merchant_id: str, suffix: str = "") -> str:
    path = f"/merchants/{_quote(merchant_id)}/messages"
    return path if suffix == "" else f"{path}{suffix}"


def _root_url_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _default_transform_response(context: MailerResponseContext, unwrap_data: bool = True) -> object:
    if not context.response.is_success:
        raise _to_mailer_error(context.response.status_code, context.payload)
    if unwrap_data and is_success_envelope(context.payload):
        payload = as_mapping(context.payload)
        return payload["data"]
    return context.payload


def _extract_data_array_response(context: MailerResponseContext) -> object:
    payload = _default_transform_response(context, unwrap_data=False)
    if isinstance(payload, list):
        return payload
    payload_mapping = as_mapping(payload)
    if isinstance(payload_mapping.get("data"), list):
        return payload_mapping["data"]
    return payload


def _to_mailer_error(status_code: int, payload: object) -> MailerError:
    message, code, details = error_envelope_message(payload)
    if message is not None:
        return MailerError(
            message,
            status_code=status_code,
            code=code,
            details=details,
            response_body=payload,
        )
    if isinstance(payload, str) and payload.strip() != "":
        return MailerError(payload, status_code=status_code, response_body=payload)
    return MailerError(
        f"Mailer request failed with status {status_code}.",
        status_code=status_code,
        response_body=payload,
    )


def _normalize_retry_policy(
    retry: RetryOptions | int | bool | None,
) -> RetryOptions:
    if retry in (None, False):
        return RetryOptions(max_attempts=1)
    if retry is True:
        return RetryOptions()
    if isinstance(retry, int):
        return RetryOptions(max_attempts=max(1, retry))
    return RetryOptions(
        max_attempts=max(1, int(retry.max_attempts)),
        delay_seconds=retry.delay_seconds,
        should_retry=retry.should_retry,
    )


def _default_should_retry(context: MailerRetryContext) -> bool:
    if context.error is not None:
        return not isinstance(context.error, MailerError)
    if context.response is None:
        return False
    return context.response.status_code in RETRYABLE_STATUS_CODES


def _default_retry_delay(attempt: int) -> float:
    return min(1.0, 0.1 * (2 ** max(0, attempt - 1)))


def _sync_should_retry(policy: RetryOptions, context: MailerRetryContext) -> bool:
    if policy.should_retry is None:
        return _default_should_retry(context)
    return _resolve_sync_value(policy.should_retry(context), "Retry predicate")


def _sync_retry_delay(policy: RetryOptions, context: MailerRetryContext) -> float:
    if policy.delay_seconds is None:
        return _default_retry_delay(context.attempt)
    if callable(policy.delay_seconds):
        return float(_resolve_sync_value(policy.delay_seconds(context), "Retry delay"))
    return float(policy.delay_seconds)


async def _async_should_retry(policy: RetryOptions, context: MailerRetryContext) -> bool:
    if policy.should_retry is None:
        return _default_should_retry(context)
    return bool(await _resolve_async_value(policy.should_retry(context)))


async def _async_retry_delay(policy: RetryOptions, context: MailerRetryContext) -> float:
    if policy.delay_seconds is None:
        return _default_retry_delay(context.attempt)
    if callable(policy.delay_seconds):
        return float(await _resolve_async_value(policy.delay_seconds(context)))
    return float(policy.delay_seconds)


def _sleep_seconds(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)


async def _async_sleep_seconds(delay: float) -> None:
    if delay > 0:
        await asyncio.sleep(delay)


def _sync_transport(
    context: MailerRequestContext,
    *,
    client: Any,
    parse_response: ResponseParser | None,
) -> MailerResponseContext:
    request_kwargs = {
        "method": context.method,
        "url": context.url,
        "headers": context.headers,
        "timeout": context.timeout_seconds,
    }
    if context.body is not UNSET:
        request_kwargs["content"] = context.body
    response = client.request(**request_kwargs)
    parser = parse_response or parse_response_body
    payload = _resolve_sync_value(
        parser(response, context),
        "Response parser",
    )
    return MailerResponseContext(request=context, response=response, payload=payload)


async def _async_transport(
    context: MailerRequestContext,
    *,
    client: Any,
    parse_response: ResponseParser | None,
) -> MailerResponseContext:
    request_kwargs = {
        "method": context.method,
        "url": context.url,
        "headers": context.headers,
        "timeout": context.timeout_seconds,
    }
    if context.body is not UNSET:
        request_kwargs["content"] = context.body
    response = await client.request(**request_kwargs)
    parser = parse_response or parse_response_body
    payload = await _resolve_async_value(parser(response, context))
    return MailerResponseContext(request=context, response=response, payload=payload)


def _sync_transform_response(
    context: MailerResponseContext,
    transform_response: ResponseTransformer | None,
    *,
    unwrap_data: bool | None,
) -> object:
    if transform_response is None:
        return _default_transform_response(context, unwrap_data=unwrap_data is not False)
    return _resolve_sync_value(transform_response(context), "Response transformer")


async def _async_transform_response(
    context: MailerResponseContext,
    transform_response: ResponseTransformer | None,
    *,
    unwrap_data: bool | None,
) -> object:
    if transform_response is None:
        return _default_transform_response(context, unwrap_data=unwrap_data is not False)
    return await _resolve_async_value(transform_response(context))


def _resolve_sync_auth_headers(
    auth: MailerAuthStrategy | bool,
    context: MailerRequestContext,
) -> httpx.Headers:
    if isinstance(auth, BearerAuthStrategy):
        token = auth.token(context) if callable(auth.token) else auth.token
        resolved_token = _resolve_sync_value(token, "Auth token")
        headers = httpx.Headers()
        headers[auth.header_name] = f"{auth.prefix} {resolved_token}"
        return headers
    if isinstance(auth, HeadersAuthStrategy):
        value = auth.headers(context) if callable(auth.headers) else auth.headers
        return httpx.Headers(_resolve_sync_value(value, "Auth headers"))
    return httpx.Headers()


async def _resolve_async_auth_headers(
    auth: MailerAuthStrategy | bool,
    context: MailerRequestContext,
) -> httpx.Headers:
    if isinstance(auth, BearerAuthStrategy):
        token = auth.token(context) if callable(auth.token) else auth.token
        resolved_token = await _resolve_async_value(token)
        headers = httpx.Headers()
        headers[auth.header_name] = f"{auth.prefix} {resolved_token}"
        return headers
    if isinstance(auth, HeadersAuthStrategy):
        value = auth.headers(context) if callable(auth.headers) else auth.headers
        return httpx.Headers(await _resolve_async_value(value))
    return httpx.Headers()


def _run_sync_middleware_stack(
    middleware: Sequence[MailerMiddleware],
    context: MailerRequestContext,
    terminal: Any,
) -> MailerResponseContext:
    handler = terminal
    for current in reversed(middleware):
        next_handler = handler

        def wrapper(
            request_context: MailerRequestContext,
            current_middleware: MailerMiddleware = current,
            downstream: Any = next_handler,
        ) -> MailerResponseContext:
            return _resolve_sync_value(
                current_middleware(request_context, downstream),
                "Middleware",
            )

        handler = wrapper
    return handler(context)


async def _run_async_middleware_stack(
    middleware: Sequence[MailerMiddleware],
    context: MailerRequestContext,
    terminal: Any,
) -> MailerResponseContext:
    handler = terminal
    for current in reversed(middleware):
        next_handler = handler

        async def wrapper(
            request_context: MailerRequestContext,
            current_middleware: MailerMiddleware = current,
            downstream: Any = next_handler,
        ) -> MailerResponseContext:
            return await _resolve_async_value(current_middleware(request_context, downstream))

        handler = wrapper
    return await handler(context)


def _resolve_sync_value(value: object, label: str) -> Any:
    if inspect.isawaitable(value):
        raise TypeError(f"{label} returned an awaitable in the sync Mailer client.")
    return value


async def _resolve_async_value(value: object) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")
