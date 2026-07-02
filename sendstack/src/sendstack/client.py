"""Sync and async SendStack clients.

Exposes the bearer-callable resource groups plus a low-level
``request(...)`` escape hatch, via a synchronous :class:`Sendstack` and an
asynchronous :class:`AsyncSendstack`, both backed by ``httpx``, with
context-manager support.

The resource classes are shared between both clients. Their methods simply
forward to ``client.request(...)``; on :class:`Sendstack` that returns the
decoded payload, and on :class:`AsyncSendstack` it returns a coroutine the
caller awaits. One definition, two execution models.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from .errors import SendstackError, is_success_envelope, to_sendstack_error
from .types import (
    DEFAULT_BASE_URL,
    UNSET,
    BearerAuthStrategy,
    HeadersAuthStrategy,
    RequestOptions,
    RetryOptions,
    SendstackAuthStrategy,
    SendstackMiddleware,
    SendstackRequestContext,
    SendstackResponseContext,
    SendstackRetryContext,
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


# --------------------------------------------------------------------------- #
# Shared base
# --------------------------------------------------------------------------- #


class _BaseClient:
    def __init__(
        self,
        auth_token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        emails: Mapping[str, str] | None = None,
        sms: Mapping[str, str] | None = None,
        whatsapp: Mapping[str, str] | None = None,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | httpx.Headers | None = None,
        query: Mapping[str, object] | None = None,
        auth: SendstackAuthStrategy | bool | None = None,
        retry: RetryOptions | int | bool | None = None,
        middleware: Sequence[SendstackMiddleware] | None = None,
        parse_response: Any = None,
        transform_response: Any = None,
    ) -> None:
        normalized_token = (auth_token or "").strip()
        self.auth_token = normalized_token
        # Per-channel defaults, applied to a send unless the call overrides them.
        self.email_from = _default_value((emails or {}).get("from"))
        self.sms_sender_id = _default_value((sms or {}).get("from"))
        self.whatsapp_from = _default_value((whatsapp or {}).get("from"))
        self.base_url = normalize_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self._default_headers = headers
        self._default_query = query
        # An explicit token defaults to bearer auth; an empty token leaves the
        # client unauthenticated unless an auth strategy or explicit
        # Authorization header is supplied per request.
        self._default_auth: SendstackAuthStrategy | bool = (
            auth
            if auth is not None
            else (False if normalized_token == "" else BearerAuthStrategy(token=normalized_token))
        )
        self._default_retry = retry
        self._default_middleware = tuple(middleware or ())
        self._default_parse_response = parse_response
        self._default_transform_response = transform_response

    # -- option resolution --------------------------------------------------- #

    def _resolve(self, options: RequestOptions | None) -> _Resolved:
        opts = options if options is not None else RequestOptions()
        return _Resolved(
            options=opts,
            timeout_seconds=(
                opts.timeout_seconds if opts.timeout_seconds is not None else self.timeout_seconds
            ),
            parse_response=(
                opts.parse_response
                if opts.parse_response is not None
                else self._default_parse_response
            ),
            transform_response=(
                opts.transform_response
                if opts.transform_response is not None
                else self._default_transform_response
            ),
            retry_policy=_normalize_retry_policy(
                opts.retry if opts.retry is not None else self._default_retry
            ),
            middleware=(*self._default_middleware, *(opts.middleware or ())),
            query=merge_query_params(self._default_query, opts.query),
        )

    def _make_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        query: Mapping[str, object] | None,
        body: object,
        headers: httpx.Headers,
        timeout_seconds: float | None,
    ) -> SendstackRequestContext:
        url = append_query_params(build_request_url(self.base_url, path), query)
        return SendstackRequestContext(
            method=method.upper(),
            path=path,
            url=url,
            headers=headers,
            body=body,
            timeout_seconds=timeout_seconds,
            attempt=attempt,
        )

    def _fallback_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        timeout_seconds: float | None,
    ) -> SendstackRequestContext:
        # Used only to feed the retry predicate/delay when the transport raised
        # before a context existed; auth resolution is intentionally skipped.
        headers = merge_headers(self._default_headers, options.headers)
        return self._make_context(
            attempt=attempt,
            method=method,
            path=path,
            query=query,
            body=UNSET,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )

    def _prepare_headers(
        self,
        *,
        options: RequestOptions,
    ) -> tuple[httpx.Headers, bool, SendstackAuthStrategy | bool]:
        headers = merge_headers(self._default_headers, options.headers)
        authenticated = True if options.authenticated is None else options.authenticated
        auth = self._default_auth if options.auth is None else options.auth

        if not authenticated:
            if "authorization" in headers:
                del headers["authorization"]
        elif not auth and not _has_explicit_auth_headers(headers):
            raise TypeError("SendStack auth is required for authenticated requests.")

        return headers, authenticated, auth

    def _finalize_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        timeout_seconds: float | None,
        headers: httpx.Headers,
    ) -> SendstackRequestContext:
        if "accept" not in headers:
            headers["accept"] = "application/json"
        if options.idempotency_key:
            headers["idempotency-key"] = options.idempotency_key
        body = prepare_request_body(options.body, headers)
        return self._make_context(
            attempt=attempt,
            method=method,
            path=path,
            query=query,
            body=body,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )


class _Resolved:
    __slots__ = (
        "options",
        "timeout_seconds",
        "parse_response",
        "transform_response",
        "retry_policy",
        "middleware",
        "query",
    )

    def __init__(
        self,
        *,
        options: RequestOptions,
        timeout_seconds: float | None,
        parse_response: Any,
        transform_response: Any,
        retry_policy: RetryOptions,
        middleware: tuple[SendstackMiddleware, ...],
        query: Mapping[str, object] | None,
    ) -> None:
        self.options = options
        self.timeout_seconds = timeout_seconds
        self.parse_response = parse_response
        self.transform_response = transform_response
        self.retry_policy = retry_policy
        self.middleware = middleware
        self.query = query


# --------------------------------------------------------------------------- #
# Sync client
# --------------------------------------------------------------------------- #


class Sendstack(_BaseClient):
    """Synchronous SendStack client backed by ``httpx.Client``."""

    def __init__(
        self,
        auth_token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        emails: Mapping[str, str] | None = None,
        sms: Mapping[str, str] | None = None,
        whatsapp: Mapping[str, str] | None = None,
        client: httpx.Client | Any | None = None,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | httpx.Headers | None = None,
        query: Mapping[str, object] | None = None,
        auth: SendstackAuthStrategy | bool | None = None,
        retry: RetryOptions | int | bool | None = None,
        middleware: Sequence[SendstackMiddleware] | None = None,
        parse_response: Any = None,
        transform_response: Any = None,
    ) -> None:
        super().__init__(
            auth_token,
            base_url=base_url,
            emails=emails,
            sms=sms,
            whatsapp=whatsapp,
            timeout_seconds=timeout_seconds,
            headers=headers,
            query=query,
            auth=auth,
            retry=retry,
            middleware=middleware,
            parse_response=parse_response,
            transform_response=transform_response,
        )
        self._client = client if client is not None else httpx.Client()
        self._owns_client = client is None
        _attach_resources(self)

    def request(self, method: str, path: str, options: RequestOptions | None = None) -> Any:
        resolved = self._resolve(options)
        opts = resolved.options
        policy = resolved.retry_policy

        for attempt in range(1, policy.max_attempts + 1):
            client = opts.client or self._client
            try:
                context = self._build_request_context(
                    attempt=attempt,
                    method=method,
                    path=path,
                    options=opts,
                    query=resolved.query,
                    timeout_seconds=resolved.timeout_seconds,
                )

                def terminal(
                    ctx: SendstackRequestContext,
                    _client: Any = client,
                    _parser: Any = resolved.parse_response,
                ) -> SendstackResponseContext:
                    return _sync_transport(ctx, client=_client, parse_response=_parser)

                response_context = _run_sync_middleware_stack(
                    resolved.middleware, context, terminal
                )

                if (
                    not response_context.response.is_success
                    and attempt < policy.max_attempts
                    and _sync_should_retry(
                        policy,
                        SendstackRetryContext(
                            request=response_context.request,
                            attempt=attempt,
                            response=response_context.response,
                        ),
                    )
                ):
                    _sleep_seconds(
                        _sync_retry_delay(
                            policy,
                            SendstackRetryContext(
                                request=response_context.request,
                                attempt=attempt,
                                response=response_context.response,
                            ),
                        )
                    )
                    continue

                return _sync_transform_response(
                    response_context,
                    resolved.transform_response,
                    unwrap_data=opts.unwrap_data,
                )
            except Exception as error:
                fallback = self._fallback_context(
                    attempt=attempt,
                    method=method,
                    path=path,
                    options=opts,
                    query=resolved.query,
                    timeout_seconds=resolved.timeout_seconds,
                )
                if attempt < policy.max_attempts and _sync_should_retry(
                    policy,
                    SendstackRetryContext(request=fallback, attempt=attempt, error=error),
                ):
                    _sleep_seconds(
                        _sync_retry_delay(
                            policy,
                            SendstackRetryContext(request=fallback, attempt=attempt, error=error),
                        )
                    )
                    continue
                raise

        # Unreachable: the final attempt always returns or re-raises; this is a
        # defensive backstop.
        raise SendstackError(  # pragma: no cover
            "SendStack request exhausted all retry attempts.", status_code=0
        )

    def _build_request_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        timeout_seconds: float | None,
    ) -> SendstackRequestContext:
        headers, _authenticated, auth = self._prepare_headers(options=options)
        if not (_authenticated and auth):
            return self._finalize_context(
                attempt=attempt,
                method=method,
                path=path,
                options=options,
                query=query,
                timeout_seconds=timeout_seconds,
                headers=headers,
            )
        auth_headers = _resolve_sync_auth_headers(
            auth,
            self._make_context(
                attempt=attempt,
                method=method,
                path=path,
                query=query,
                body=UNSET,
                headers=headers,
                timeout_seconds=timeout_seconds,
            ),
        )
        headers.update(auth_headers)
        return self._finalize_context(
            attempt=attempt,
            method=method,
            path=path,
            options=options,
            query=query,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Sendstack:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Async client
# --------------------------------------------------------------------------- #


class AsyncSendstack(_BaseClient):
    """Asynchronous SendStack client backed by ``httpx.AsyncClient``."""

    def __init__(
        self,
        auth_token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        emails: Mapping[str, str] | None = None,
        sms: Mapping[str, str] | None = None,
        whatsapp: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | Any | None = None,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | httpx.Headers | None = None,
        query: Mapping[str, object] | None = None,
        auth: SendstackAuthStrategy | bool | None = None,
        retry: RetryOptions | int | bool | None = None,
        middleware: Sequence[SendstackMiddleware] | None = None,
        parse_response: Any = None,
        transform_response: Any = None,
    ) -> None:
        super().__init__(
            auth_token,
            base_url=base_url,
            emails=emails,
            sms=sms,
            whatsapp=whatsapp,
            timeout_seconds=timeout_seconds,
            headers=headers,
            query=query,
            auth=auth,
            retry=retry,
            middleware=middleware,
            parse_response=parse_response,
            transform_response=transform_response,
        )
        self._client = client if client is not None else httpx.AsyncClient()
        self._owns_client = client is None
        _attach_resources(self)

    async def request(self, method: str, path: str, options: RequestOptions | None = None) -> Any:
        resolved = self._resolve(options)
        opts = resolved.options
        policy = resolved.retry_policy

        for attempt in range(1, policy.max_attempts + 1):
            client = opts.client or self._client
            try:
                context = await self._build_request_context(
                    attempt=attempt,
                    method=method,
                    path=path,
                    options=opts,
                    query=resolved.query,
                    timeout_seconds=resolved.timeout_seconds,
                )

                async def terminal(
                    ctx: SendstackRequestContext,
                    _client: Any = client,
                    _parser: Any = resolved.parse_response,
                ) -> SendstackResponseContext:
                    return await _async_transport(ctx, client=_client, parse_response=_parser)

                response_context = await _run_async_middleware_stack(
                    resolved.middleware, context, terminal
                )

                if (
                    not response_context.response.is_success
                    and attempt < policy.max_attempts
                    and await _async_should_retry(
                        policy,
                        SendstackRetryContext(
                            request=response_context.request,
                            attempt=attempt,
                            response=response_context.response,
                        ),
                    )
                ):
                    await _async_sleep_seconds(
                        await _async_retry_delay(
                            policy,
                            SendstackRetryContext(
                                request=response_context.request,
                                attempt=attempt,
                                response=response_context.response,
                            ),
                        )
                    )
                    continue

                return await _async_transform_response(
                    response_context,
                    resolved.transform_response,
                    unwrap_data=opts.unwrap_data,
                )
            except Exception as error:
                fallback = self._fallback_context(
                    attempt=attempt,
                    method=method,
                    path=path,
                    options=opts,
                    query=resolved.query,
                    timeout_seconds=resolved.timeout_seconds,
                )
                if attempt < policy.max_attempts and await _async_should_retry(
                    policy,
                    SendstackRetryContext(request=fallback, attempt=attempt, error=error),
                ):
                    await _async_sleep_seconds(
                        await _async_retry_delay(
                            policy,
                            SendstackRetryContext(request=fallback, attempt=attempt, error=error),
                        )
                    )
                    continue
                raise

        # Unreachable: the final attempt always returns or re-raises; this is a
        # defensive backstop.
        raise SendstackError(  # pragma: no cover
            "SendStack request exhausted all retry attempts.", status_code=0
        )

    async def _build_request_context(
        self,
        *,
        attempt: int,
        method: str,
        path: str,
        options: RequestOptions,
        query: Mapping[str, object] | None,
        timeout_seconds: float | None,
    ) -> SendstackRequestContext:
        headers, _authenticated, auth = self._prepare_headers(options=options)
        if not (_authenticated and auth):
            return self._finalize_context(
                attempt=attempt,
                method=method,
                path=path,
                options=options,
                query=query,
                timeout_seconds=timeout_seconds,
                headers=headers,
            )
        auth_headers = await _resolve_async_auth_headers(
            auth,
            self._make_context(
                attempt=attempt,
                method=method,
                path=path,
                query=query,
                body=UNSET,
                headers=headers,
                timeout_seconds=timeout_seconds,
            ),
        )
        headers.update(auth_headers)
        return self._finalize_context(
            attempt=attempt,
            method=method,
            path=path,
            options=options,
            query=query,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncSendstack:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- #
# Resources (shared between sync and async clients)
# --------------------------------------------------------------------------- #

_Client = Sendstack | AsyncSendstack


def _attach_resources(client: _Client) -> None:
    client.attachments = _Attachments(client)
    client.emails = _Emails(client)
    client.sms = _Sms(client)
    client.whatsapp = _WhatsApp(client)
    client.whatsapp_senders = _WhatsAppSenders(client)
    client.whatsappSenders = client.whatsapp_senders  # camelCase alias
    client.senders = _Senders(client)
    client.billing = _Billing(client)
    client.domains = _Domains(client)
    client.templates = _Templates(client)
    client.webhooks = _Webhooks(client)
    client.webhook_events = _WebhookEvents(client)
    client.webhookEvents = client.webhook_events  # camelCase alias
    client.suppressions = _Suppressions(client)


class _Attachments:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def upload(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST",
            "/attachments",
            _with(options, body=_normalize_upload_attachment_request(request)),
        )


class _Emails:
    def __init__(self, client: _Client) -> None:
        self._client = client
        self.sendBatch = self.send_batch  # camelCase alias

    def send(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST",
            "/emails",
            _with(options, body=_normalize_send_email_request(request, self._client.email_from)),
        )

    def send_batch(
        self,
        request: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "POST",
            "/emails/batch",
            _with(options, body=_normalize_send_email_batch(request, self._client.email_from)),
        )

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        status: str | None = None,
    ) -> Any:
        query = merge_query_params(
            {"limit": limit, "cursor": cursor, "status": status},
            options.query if options else None,
        )
        return self._client.request("GET", "/emails", _with(options, query=query))

    def get(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/emails/{_quote(message_id)}", options)

    def events(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/emails/{_quote(message_id)}/events", options)

    def cancel(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/emails/{_quote(message_id)}/cancel", options)

    def requeue(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/emails/{_quote(message_id)}/requeue", options)


class _Sms:
    def __init__(self, client: _Client) -> None:
        self._client = client
        self.sendBatch = self.send_batch  # camelCase alias

    def send(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST",
            "/sms",
            _with(options, body=_normalize_send_sms_request(request, self._client.sms_sender_id)),
        )

    def send_batch(
        self,
        request: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "POST",
            "/sms/batch",
            _with(options, body=_normalize_send_sms_batch(request, self._client.sms_sender_id)),
        )

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        status: str | None = None,
    ) -> Any:
        query = merge_query_params(
            {"limit": limit, "cursor": cursor, "status": status},
            options.query if options else None,
        )
        return self._client.request("GET", "/sms", _with(options, query=query))

    def get(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/sms/{_quote(message_id)}", options)

    def events(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/sms/{_quote(message_id)}/events", options)

    def cancel(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/sms/{_quote(message_id)}/cancel", options)

    def requeue(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/sms/{_quote(message_id)}/requeue", options)


class _WhatsApp:
    def __init__(self, client: _Client) -> None:
        self._client = client
        self.sendBatch = self.send_batch  # camelCase alias

    def send(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        body = _normalize_send_whatsapp_request(request, self._client.whatsapp_from)
        return self._client.request("POST", "/whatsapp", _with(options, body=body))

    def send_batch(
        self,
        request: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        body = _normalize_send_whatsapp_batch(request, self._client.whatsapp_from)
        return self._client.request("POST", "/whatsapp/batch", _with(options, body=body))

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        status: str | None = None,
    ) -> Any:
        query = merge_query_params(
            {"limit": limit, "cursor": cursor, "status": status},
            options.query if options else None,
        )
        return self._client.request("GET", "/whatsapp", _with(options, query=query))

    def get(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/whatsapp/{_quote(message_id)}", options)

    def events(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/whatsapp/{_quote(message_id)}/events", options)

    def cancel(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/whatsapp/{_quote(message_id)}/cancel", options)

    def requeue(self, message_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/whatsapp/{_quote(message_id)}/requeue", options)


class _WhatsAppSenders:
    def __init__(self, client: _Client) -> None:
        self._client = client
        self.setDefault = self.set_default  # camelCase alias

    def list(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/whatsapp/senders", options)

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST",
            "/whatsapp/senders",
            _with(options, body=_normalize_create_whatsapp_sender_request(request)),
        )

    def get(self, sender_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/whatsapp/senders/{_quote(sender_id)}", options)

    def set_default(self, sender_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST", f"/whatsapp/senders/{_quote(sender_id)}/default", options
        )

    def remove(self, sender_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("DELETE", f"/whatsapp/senders/{_quote(sender_id)}", options)


class _Senders:
    def __init__(self, client: _Client) -> None:
        self._client = client
        self.uploadKyc = self.upload_kyc  # camelCase alias
        self.authorizationLetter = self.authorization_letter  # camelCase alias

    def options(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/sms/senders/options", options)

    def list(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/sms/senders", options)

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        body = _normalize_create_sender_id_request(request)
        return self._client.request("POST", "/sms/senders", _with(options, body=body))

    def get(self, sender_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/sms/senders/{_quote(sender_id)}", options)

    def upload_kyc(
        self,
        sender_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "POST",
            f"/sms/senders/{_quote(sender_id)}/kyc",
            _with(options, body=_normalize_upload_sender_kyc_request(request)),
        )

    def pay(
        self,
        sender_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "POST", f"/sms/senders/{_quote(sender_id)}/pay", _with(options, body=dict(request))
        )

    def authorization_letter(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/sms/authorization-letter", options)


class _Billing:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def credits(self, options: RequestOptions | None = None, *, channel: str | None = None) -> Any:
        query = merge_query_params({"channel": channel}, options.query if options else None)
        return self._client.request("GET", "/billing/credits", _with(options, query=query))

    def products(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/billing/products", options)

    def checkout(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST", "/billing/checkout", _with(options, body=_normalize_checkout_request(request))
        )

    def payments(self, options: RequestOptions | None = None, *, limit: int | None = None) -> Any:
        query = merge_query_params({"limit": limit}, options.query if options else None)
        return self._client.request("GET", "/billing/payments", _with(options, query=query))

    def payment(self, payment_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/billing/payments/{_quote(payment_id)}", options)

    def purchases(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/billing/purchases", options)


class _Domains:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST", "/domains", _with(options, body=_normalize_domain_request(request))
        )

    def list(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/domains", options)

    def get(self, domain_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/domains/{_quote(domain_id)}", options)

    def verify(self, domain_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/domains/{_quote(domain_id)}/verify", options)


class _PublishableTemplate(dict):
    """Created template (sync client). Call ``.publish()`` to publish it in a follow-up
    request: ``client.templates.create({...}).publish()``."""

    def __init__(self, data: Any, templates: _Templates, options: RequestOptions | None) -> None:
        super().__init__(data)
        self._templates = templates
        self._options = options

    def publish(self, options: RequestOptions | None = None) -> Any:
        return self._templates.publish(self["id"], options or self._options)


class _AsyncPublishableTemplate:
    """Awaitable created template (async client). ``await client.templates.create({...})``
    yields the template; ``.publish()`` creates then publishes in one expression."""

    def __init__(self, pending: Any, templates: _Templates, options: RequestOptions | None) -> None:
        self._pending = pending
        self._templates = templates
        self._options = options

    def __await__(self) -> Any:
        return self._pending.__await__()

    async def publish(self, options: RequestOptions | None = None) -> Any:
        created = await self._pending
        return await self._templates.publish(created["id"], options or self._options)


class _Templates:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        created = self._client.request(
            "POST", "/templates", _with(options, body=_normalize_template_request(request))
        )
        if inspect.isawaitable(created):
            return _AsyncPublishableTemplate(created, self, options)
        return _PublishableTemplate(created, self, options)

    def list(
        self,
        options: RequestOptions | None = None,
        *,
        channel: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Any:
        query = merge_query_params(
            {"channel": channel, "status": status, "limit": limit, "cursor": cursor},
            options.query if options else None,
        )
        return self._client.request("GET", "/templates", _with(options, query=query))

    def get(self, template_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", f"/templates/{_quote(template_id)}", options)

    def update(
        self,
        template_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "PATCH",
            f"/templates/{_quote(template_id)}",
            _with(options, body=_normalize_template_request(request)),
        )

    def remove(self, template_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("DELETE", f"/templates/{_quote(template_id)}", options)

    def publish(self, template_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/templates/{_quote(template_id)}/publish", options)

    def duplicate(
        self,
        template_id: str,
        request: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "POST",
            f"/templates/{_quote(template_id)}/duplicate",
            _with(options, body=dict(request or {})),
        )

    def preview(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST",
            "/templates/preview",
            _with(options, body=_normalize_template_preview_request(request)),
        )


class _Webhooks:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def create(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request(
            "POST", "/webhook-endpoints", _with(options, body=_normalize_webhook_request(request))
        )

    def list(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/webhook-endpoints", options)

    def update(
        self,
        webhook_id: str,
        request: Mapping[str, Any],
        options: RequestOptions | None = None,
    ) -> Any:
        return self._client.request(
            "PATCH",
            f"/webhook-endpoints/{_quote(webhook_id)}",
            _with(options, body=_normalize_webhook_request(request)),
        )

    def remove(self, webhook_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("DELETE", f"/webhook-endpoints/{_quote(webhook_id)}", options)


class _WebhookEvents:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def retry(self, event_id: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", f"/events/{_quote(event_id)}/retry", options)


class _Suppressions:
    def __init__(self, client: _Client) -> None:
        self._client = client

    def add(self, request: Mapping[str, Any], options: RequestOptions | None = None) -> Any:
        return self._client.request("POST", "/suppressions", _with(options, body=dict(request)))

    def list(self, options: RequestOptions | None = None) -> Any:
        return self._client.request("GET", "/suppressions", options)

    def remove(self, recipient: str, options: RequestOptions | None = None) -> Any:
        return self._client.request("DELETE", f"/suppressions/{_quote(recipient)}", options)


# --------------------------------------------------------------------------- #
# Payload normalization (camelCase aliases -> wire field names)
# --------------------------------------------------------------------------- #


def _with(options: RequestOptions | None, **changes: object) -> RequestOptions:
    base = options if options is not None else RequestOptions()
    return replace(base, **changes)


def _default_value(value: str | None) -> str | None:
    return (value or "").strip() or None


def _normalize_send_email_request(
    request: Mapping[str, Any], default_from: str | None = None
) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "replyTo", "reply_to")
    _rename(payload, "trackOpens", "track_opens")
    _rename(payload, "trackClicks", "track_clicks")
    _rename(payload, "providerId", "provider_id")
    _rename(payload, "templateId", "template_id")
    _rename(payload, "templateData", "template_data")
    _rename(payload, "scheduledAt", "scheduled_at")

    scheduled_at = payload.get("scheduled_at")
    if isinstance(scheduled_at, datetime):
        payload["scheduled_at"] = serialize_datetime(scheduled_at)

    attachments = payload.get("attachments")
    if isinstance(attachments, Sequence) and not isinstance(attachments, (str, bytes, bytearray)):
        payload["attachments"] = [
            _normalize_email_attachment(attachment)
            if isinstance(attachment, Mapping)
            else attachment
            for attachment in attachments
        ]

    if default_from is not None and payload.get("from") is None:
        payload["from"] = default_from
    return payload


def _normalize_email_attachment(attachment: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(attachment)
    _rename(payload, "contentBase64", "content_base64")
    _rename(payload, "attachmentId", "attachment_id")
    _rename(payload, "contentType", "content_type")
    _rename(payload, "contentId", "content_id")
    return payload


def _normalize_upload_attachment_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "contentBase64", "content_base64")
    _rename(payload, "contentType", "content_type")
    return payload


def _normalize_send_sms_request(
    request: Mapping[str, Any], default_sender_id: str | None = None
) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "providerId", "provider_id")
    _rename(payload, "templateId", "template_id")
    _rename(payload, "templateData", "template_data")
    _rename(payload, "scheduledAt", "scheduled_at")

    scheduled_at = payload.get("scheduled_at")
    if isinstance(scheduled_at, datetime):
        payload["scheduled_at"] = serialize_datetime(scheduled_at)

    if default_sender_id is not None and payload.get("from") is None:
        payload["from"] = default_sender_id
    return payload


def _normalize_send_sms_batch(
    request: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    default_sender_id: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(request, Mapping):
        messages = request.get("messages", [])
        return {
            "messages": [_normalize_send_sms_request(m, default_sender_id) for m in messages]
        }
    return [_normalize_send_sms_request(m, default_sender_id) for m in request]


def _normalize_send_whatsapp_request(
    request: Mapping[str, Any], default_from: str | None = None
) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "providerId", "provider_id")
    _rename(payload, "templateId", "template_id")
    _rename(payload, "templateData", "template_data")
    _rename(payload, "scheduledAt", "scheduled_at")

    scheduled_at = payload.get("scheduled_at")
    if isinstance(scheduled_at, datetime):
        payload["scheduled_at"] = serialize_datetime(scheduled_at)

    if default_from is not None and payload.get("from") is None:
        payload["from"] = default_from
    return payload


def _normalize_send_whatsapp_batch(
    request: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    default_from: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(request, Mapping):
        messages = request.get("messages", [])
        return {
            "messages": [_normalize_send_whatsapp_request(m, default_from) for m in messages]
        }
    return [_normalize_send_whatsapp_request(m, default_from) for m in request]


def _normalize_create_whatsapp_sender_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "phoneNumberId", "phone_number_id")
    _rename(payload, "wabaId", "waba_id")
    _rename(payload, "accessToken", "access_token")
    _rename(payload, "displayName", "display_name")
    _rename(payload, "isDefault", "is_default")
    return payload


def _normalize_create_sender_id_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "requestedId", "requested_id")
    _rename(payload, "entityType", "entity_type")
    return payload


def _normalize_kyc_file(file: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(file)
    _rename(payload, "contentBase64", "content_base64")
    _rename(payload, "contentType", "content_type")
    return payload


def _normalize_upload_sender_kyc_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "authLetter", "auth_letter")

    documents = payload.get("documents")
    if isinstance(documents, Sequence) and not isinstance(documents, (str, bytes, bytearray)):
        payload["documents"] = [
            _normalize_kyc_file(doc) if isinstance(doc, Mapping) else doc for doc in documents
        ]

    auth_letter = payload.get("auth_letter")
    if isinstance(auth_letter, Mapping):
        payload["auth_letter"] = _normalize_kyc_file(auth_letter)

    return payload


def _normalize_checkout_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "productCode", "product_code")
    return payload


def _normalize_template_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "sampleData", "sample_data")
    _rename(payload, "fromName", "from_name")
    _rename(payload, "replyTo", "reply_to")
    _rename(payload, "templateName", "template_name")
    _rename(payload, "bodyVariables", "body_variables")
    return payload


def _normalize_template_preview_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "templateId", "template_id")
    _rename(payload, "templateData", "template_data")
    return payload


def _normalize_domain_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "providerId", "provider_id")
    _rename(payload, "customReturnPath", "custom_return_path")
    return payload


def _normalize_webhook_request(request: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    _rename(payload, "eventTypes", "event_types")
    return payload


def _normalize_send_email_batch(
    request: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    default_from: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(request, Mapping):
        emails = request.get("emails", [])
        return {"emails": [_normalize_send_email_request(e, default_from) for e in emails]}
    return [_normalize_send_email_request(e, default_from) for e in request]


def _rename(payload: dict[str, Any], camel_name: str, snake_name: str) -> None:
    if camel_name in payload and snake_name not in payload:
        payload[snake_name] = payload.pop(camel_name)


def _has_explicit_auth_headers(headers: httpx.Headers) -> bool:
    return "authorization" in headers


def _quote(value: str) -> str:
    return quote(value, safe="")


# --------------------------------------------------------------------------- #
# Response transform + retry policy
# --------------------------------------------------------------------------- #


def _default_transform_response(
    context: SendstackResponseContext, unwrap_data: bool = True
) -> object:
    if not context.response.is_success:
        raise to_sendstack_error(context.response.status_code, context.payload)
    if unwrap_data and is_success_envelope(context.payload):
        return as_mapping(context.payload)["data"]
    return context.payload


def _sync_transform_response(
    context: SendstackResponseContext,
    transform_response: Any,
    *,
    unwrap_data: bool | None,
) -> object:
    if transform_response is None:
        return _default_transform_response(context, unwrap_data=unwrap_data is not False)
    return _resolve_sync_value(transform_response(context), "Response transformer")


async def _async_transform_response(
    context: SendstackResponseContext,
    transform_response: Any,
    *,
    unwrap_data: bool | None,
) -> object:
    if transform_response is None:
        return _default_transform_response(context, unwrap_data=unwrap_data is not False)
    return await _resolve_async_value(transform_response(context))


def _normalize_retry_policy(retry: RetryOptions | int | bool | None) -> RetryOptions:
    if retry is None or retry is False:
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


def _default_should_retry(context: SendstackRetryContext) -> bool:
    if context.error is not None:
        return not isinstance(context.error, SendstackError)
    if context.response is None:
        return False
    return context.response.status_code in RETRYABLE_STATUS_CODES


def _default_retry_delay(attempt: int) -> float:
    return min(1.0, 0.1 * (2 ** max(0, attempt - 1)))


def _sync_should_retry(policy: RetryOptions, context: SendstackRetryContext) -> bool:
    if policy.should_retry is None:
        return _default_should_retry(context)
    return bool(_resolve_sync_value(policy.should_retry(context), "Retry predicate"))


def _sync_retry_delay(policy: RetryOptions, context: SendstackRetryContext) -> float:
    if policy.delay_seconds is None:
        return _default_retry_delay(context.attempt)
    if callable(policy.delay_seconds):
        return max(0.0, float(_resolve_sync_value(policy.delay_seconds(context), "Retry delay")))
    return max(0.0, float(policy.delay_seconds))


async def _async_should_retry(policy: RetryOptions, context: SendstackRetryContext) -> bool:
    if policy.should_retry is None:
        return _default_should_retry(context)
    return bool(await _resolve_async_value(policy.should_retry(context)))


async def _async_retry_delay(policy: RetryOptions, context: SendstackRetryContext) -> float:
    if policy.delay_seconds is None:
        return _default_retry_delay(context.attempt)
    if callable(policy.delay_seconds):
        return max(0.0, float(await _resolve_async_value(policy.delay_seconds(context))))
    return max(0.0, float(policy.delay_seconds))


def _sleep_seconds(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)


async def _async_sleep_seconds(delay: float) -> None:
    if delay > 0:
        await asyncio.sleep(delay)


# --------------------------------------------------------------------------- #
# Transport + middleware + auth resolution
# --------------------------------------------------------------------------- #


def _sync_transport(
    context: SendstackRequestContext, *, client: Any, parse_response: Any
) -> SendstackResponseContext:
    response = client.request(**_request_kwargs(context))
    parser = parse_response or parse_response_body
    payload = _resolve_sync_value(parser(response, context), "Response parser")
    return SendstackResponseContext(request=context, response=response, payload=payload)


async def _async_transport(
    context: SendstackRequestContext, *, client: Any, parse_response: Any
) -> SendstackResponseContext:
    response = await client.request(**_request_kwargs(context))
    parser = parse_response or parse_response_body
    payload = await _resolve_async_value(parser(response, context))
    return SendstackResponseContext(request=context, response=response, payload=payload)


def _request_kwargs(context: SendstackRequestContext) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "method": context.method,
        "url": context.url,
        "headers": context.headers,
        "timeout": context.timeout_seconds,
    }
    if context.body is not UNSET:
        kwargs["content"] = context.body
    return kwargs


def _run_sync_middleware_stack(
    middleware: Sequence[SendstackMiddleware],
    context: SendstackRequestContext,
    terminal: Any,
) -> SendstackResponseContext:
    handler = terminal
    for current in reversed(middleware):
        next_handler = handler

        def wrapper(
            request_context: SendstackRequestContext,
            current_middleware: SendstackMiddleware = current,
            downstream: Any = next_handler,
        ) -> SendstackResponseContext:
            return _resolve_sync_value(
                current_middleware(request_context, downstream), "Middleware"
            )

        handler = wrapper
    return handler(context)


async def _run_async_middleware_stack(
    middleware: Sequence[SendstackMiddleware],
    context: SendstackRequestContext,
    terminal: Any,
) -> SendstackResponseContext:
    handler = terminal
    for current in reversed(middleware):
        next_handler = handler

        async def wrapper(
            request_context: SendstackRequestContext,
            current_middleware: SendstackMiddleware = current,
            downstream: Any = next_handler,
        ) -> SendstackResponseContext:
            return await _resolve_async_value(current_middleware(request_context, downstream))

        handler = wrapper
    return await handler(context)


def _resolve_sync_auth_headers(
    auth: SendstackAuthStrategy | bool, context: SendstackRequestContext
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
    auth: SendstackAuthStrategy | bool, context: SendstackRequestContext
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


def _resolve_sync_value(value: object, label: str) -> Any:
    if inspect.isawaitable(value):
        raise TypeError(f"{label} returned an awaitable in the synchronous Sendstack client.")
    return value


async def _resolve_async_value(value: object) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


# Alternative class names.
SendstackClient = Sendstack
AsyncSendstackClient = AsyncSendstack
