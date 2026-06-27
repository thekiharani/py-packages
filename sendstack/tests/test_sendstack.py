"""Behavioural tests for the SendStack Python SDK (sync + async)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

import sendstack.client as cm
from sendstack import (
    AsyncSendstack,
    BearerAuthStrategy,
    HeadersAuthStrategy,
    RequestOptions,
    RetryOptions,
    Sendstack,
    SendstackError,
)
from sendstack.errors import (
    is_error_envelope,
    is_success_envelope,
    to_sendstack_error,
)
from sendstack.types import (
    SendstackRequestContext,
    SendstackRetryContext,
)
from sendstack.utils import (
    append_query_params,
    as_mapping,
    build_request_url,
    json_default,
    merge_headers,
    merge_query_params,
    normalize_base_url,
    normalize_query_pairs,
    parse_response_body,
    prepare_request_body,
    serialize_datetime,
    serialize_query_value,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def ok(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def ok_data(data: Any, status: int = 200) -> httpx.Response:
    return ok({"ok": True, "data": data}, status)


class _Awaitable:
    """An awaitable that is *not* a coroutine (so it never warns if dropped)."""

    def __await__(self):  # pragma: no cover - never actually awaited
        return iter(())


def _handler(responses: list[Any], calls: list[httpx.Request]):
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        item = queue.pop(0) if queue else ok_data({})
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)
        return item

    return handler


def make_sync(
    responses: list[Any] | None = None,
    *,
    token: str | None = "tok",
    **kwargs: Any,
) -> tuple[Sendstack, list[httpx.Request], httpx.Client]:
    calls: list[httpx.Request] = []
    http = httpx.Client(transport=httpx.MockTransport(_handler(responses or [], calls)))
    client = Sendstack(token, client=http, **kwargs)
    return client, calls, http


def run_async(coro_fn) -> Any:
    return asyncio.run(coro_fn())


def make_async_http(responses: list[Any], calls: list[httpx.Request]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_handler(responses, calls)))


# --------------------------------------------------------------------------- #
# Emails
# --------------------------------------------------------------------------- #


def test_send_email_aliases_and_unwraps():
    client, calls, http = make_sync([ok_data({"id": "m_1", "status": "queued"})])
    try:
        result = client.emails.send(
            {
                "from": "a@x.com",
                "to": "b@y.com",
                "subject": "Hi",
                "replyTo": "r@x.com",
                "trackOpens": True,
                "scheduledAt": datetime(2026, 1, 1, tzinfo=UTC),
                "attachments": [
                    {
                        "filename": "a.pdf",
                        "attachmentId": "att_1",
                        "contentType": "application/pdf",
                    },
                    "not-a-mapping",
                ],
                "text": "hi",
            }
        )
    finally:
        http.close()

    assert result == {"id": "m_1", "status": "queued"}
    request = calls[0]
    assert str(request.url) == "https://sendstack.norialabs.com/api/v1/emails"
    assert request.method == "POST"
    assert request.headers["authorization"] == "Bearer tok"
    assert request.headers["accept"] == "application/json"
    body = json.loads(request.content)
    assert body["reply_to"] == "r@x.com"
    assert body["track_opens"] is True
    assert body["scheduled_at"] == "2026-01-01T00:00:00.000Z"
    assert body["attachments"][0] == {
        "filename": "a.pdf",
        "attachment_id": "att_1",
        "content_type": "application/pdf",
    }
    assert body["attachments"][1] == "not-a-mapping"


def test_send_batch_list_and_dict_forms():
    client, calls, http = make_sync(
        [
            ok_data({"batch_id": "b1", "data": [{"id": "1", "status": "queued"}]}),
            ok_data({"batch_id": "b2", "data": []}),
        ]
    )
    try:
        first = client.emails.send_batch([{"from": "a", "to": "b", "replyTo": "r", "text": "x"}])
        second = client.emails.sendBatch({"emails": [{"from": "a", "to": "b", "text": "y"}]})
    finally:
        http.close()

    assert first["batch_id"] == "b1"
    assert second["batch_id"] == "b2"
    assert json.loads(calls[0].content) == [{"from": "a", "to": "b", "reply_to": "r", "text": "x"}]
    assert json.loads(calls[1].content) == {"emails": [{"from": "a", "to": "b", "text": "y"}]}


def test_emails_list_query_merges():
    client, calls, http = make_sync([ok_data({"data": [], "next_cursor": None})])
    try:
        client.emails.list(RequestOptions(query={"extra": "1"}), limit=10, status="queued")
    finally:
        http.close()
    params = dict(calls[0].url.params)
    assert params == {"extra": "1", "limit": "10", "status": "queued"}


def test_emails_get_events_cancel_requeue():
    client, calls, http = make_sync(
        [
            ok_data({"id": "m1"}),
            ok_data({"data": [{"id": "e1", "type": "email.sent"}]}),
            ok_data({"id": "m1", "status": "canceled"}),
            ok_data({"id": "m1", "status": "queued"}),
        ]
    )
    try:
        assert client.emails.get("m 1")["id"] == "m1"
        assert client.emails.events("m1")["data"][0]["id"] == "e1"
        assert client.emails.cancel("m1")["status"] == "canceled"
        assert client.emails.requeue("m1")["status"] == "queued"
    finally:
        http.close()
    assert calls[0].url.path == "/api/v1/emails/m 1"  # decoded back by httpx (sent percent-encoded)
    assert calls[1].url.path == "/api/v1/emails/m1/events"
    assert calls[2].method == "POST" and calls[2].url.path == "/api/v1/emails/m1/cancel"
    assert calls[3].url.path == "/api/v1/emails/m1/requeue"


# --------------------------------------------------------------------------- #
# SMS
# --------------------------------------------------------------------------- #


def test_sms_aliases_sender_default_and_override():
    client, calls, http = make_sync(
        [
            ok_data({"id": "sms_1", "status": "queued"}),
            ok_data({"id": "sms_2", "status": "queued"}),
            ok_data({"batch_id": "b1", "data": []}),
            ok_data({"batch_id": "b2", "data": []}),
        ],
        sender_id="NORIA",
    )
    try:
        client.sms.send(
            {
                "to": "+254700000000",
                "body": "Your code is 1234",
                "providerId": "prov_1",
                "templateId": "tpl_otp",
                "templateData": {"code": "1234"},
                "scheduledAt": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
        client.sms.send({"to": "+254700000001", "body": "Hi", "senderId": "OTHER"})
        client.sms.send_batch(
            {
                "messages": [
                    {"to": "+254700000002", "body": "One"},
                    {"to": "+254700000003", "body": "Two", "senderId": "KEEP"},
                ]
            }
        )
        client.sms.sendBatch([{"to": "+254700000004", "body": "Solo"}])
    finally:
        http.close()

    assert client.sender_id == "NORIA"
    assert json.loads(calls[0].content) == {
        "to": "+254700000000",
        "body": "Your code is 1234",
        "provider_id": "prov_1",
        "template_id": "tpl_otp",
        "template_data": {"code": "1234"},
        "scheduled_at": "2026-01-01T00:00:00.000Z",
        "sender_id": "NORIA",
    }
    assert calls[0].url.path == "/api/v1/sms"
    assert json.loads(calls[1].content)["sender_id"] == "OTHER"
    assert json.loads(calls[2].content) == {
        "messages": [
            {"to": "+254700000002", "body": "One", "sender_id": "NORIA"},
            {"to": "+254700000003", "body": "Two", "sender_id": "KEEP"},
        ]
    }
    assert calls[2].url.path == "/api/v1/sms/batch"
    assert json.loads(calls[3].content) == [
        {"to": "+254700000004", "body": "Solo", "sender_id": "NORIA"}
    ]


def test_sms_without_client_sender_omits_it_and_list_get_events_cancel_requeue():
    client, calls, http = make_sync(
        [
            ok_data({"id": "sms_1", "status": "queued"}),
            ok_data({"data": [], "next_cursor": None}),
            ok_data({"id": "sms_1"}),
            ok_data({"data": [{"id": "e1", "type": "sms.delivered"}]}),
            ok_data({"id": "sms_1", "status": "canceled"}),
            ok_data({"id": "sms_1", "status": "queued"}),
        ]
    )
    try:
        client.sms.send({"to": "+254700000000", "body": "Hi"})
        client.sms.list(RequestOptions(query={"extra": "1"}), limit=10, status="sent")
        client.sms.get("sms 1")
        client.sms.events("sms_1")
        client.sms.cancel("sms_1")
        client.sms.requeue("sms_1")
    finally:
        http.close()

    assert client.sender_id is None
    assert json.loads(calls[0].content) == {"to": "+254700000000", "body": "Hi"}
    assert dict(calls[1].url.params) == {"extra": "1", "limit": "10", "status": "sent"}
    assert calls[2].url.path == "/api/v1/sms/sms 1"
    assert calls[3].url.path == "/api/v1/sms/sms_1/events"
    assert calls[4].method == "POST" and calls[4].url.path == "/api/v1/sms/sms_1/cancel"
    assert calls[5].url.path == "/api/v1/sms/sms_1/requeue"


# --------------------------------------------------------------------------- #
# Domains / Templates / Webhooks / Suppressions / Attachments
# --------------------------------------------------------------------------- #


def test_domains_resource():
    client, calls, http = make_sync(
        [
            ok_data({"id": "d1"}),
            ok_data({"data": []}),
            ok_data({"id": "d1"}),
            ok_data({"id": "d1", "status": "verified"}),
        ]
    )
    try:
        client.domains.create({"domain": "x.com", "providerId": "p1", "customReturnPath": "bounce"})
        client.domains.list()
        client.domains.get("d1")
        client.domains.verify("d1")
    finally:
        http.close()
    assert json.loads(calls[0].content) == {
        "domain": "x.com",
        "provider_id": "p1",
        "custom_return_path": "bounce",
    }
    assert calls[1].method == "GET" and calls[1].url.path == "/api/v1/domains"
    assert calls[3].url.path == "/api/v1/domains/d1/verify"


def test_templates_resource_including_delete_returns_none():
    client, calls, http = make_sync(
        [
            ok_data({"id": "t1"}),
            ok_data({"data": []}),
            ok_data({"id": "t1"}),
            ok_data({"id": "t1", "subject": "New"}),
            httpx.Response(204, content=b""),
        ]
    )
    try:
        client.templates.create({"name": "Welcome", "subject": "Hi"})
        client.templates.list()
        client.templates.get("t1")
        client.templates.update("t1", {"subject": "New"})
        removed = client.templates.remove("t1")
    finally:
        http.close()
    assert removed is None
    assert calls[3].method == "PATCH" and calls[3].url.path == "/api/v1/templates/t1"
    assert calls[4].method == "DELETE"


def test_templates_preview_channel_filter_and_sample_data_alias():
    client, calls, http = make_sync(
        [
            ok_data(
                {
                    "channel": "sms",
                    "subject": None,
                    "html": None,
                    "text": None,
                    "body": "Your code is 1234",
                    "segments": 1,
                    "variables": ["code"],
                }
            ),
            ok_data({"id": "t1"}),
            ok_data({"data": []}),
        ]
    )
    try:
        preview = client.templates.preview(
            {"templateId": "tpl_otp", "data": {"code": "1234"}}
        )
        client.templates.create(
            {
                "channel": "sms",
                "name": "otp",
                "body": "Your code is {{ code }}",
                "sampleData": {"code": "1234"},
            }
        )
        client.templates.list(channel="sms")
    finally:
        http.close()

    assert preview["segments"] == 1
    assert calls[0].method == "POST" and calls[0].url.path == "/api/v1/templates/preview"
    assert json.loads(calls[0].content) == {"template_id": "tpl_otp", "data": {"code": "1234"}}
    assert json.loads(calls[1].content) == {
        "channel": "sms",
        "name": "otp",
        "body": "Your code is {{ code }}",
        "sample_data": {"code": "1234"},
    }
    assert dict(calls[2].url.params) == {"channel": "sms"}


def test_webhooks_resource_event_types_alias():
    client, calls, http = make_sync(
        [
            ok_data({"id": "wh"}),
            ok_data({"data": []}),
            ok_data({"id": "wh", "enabled": False}),
            httpx.Response(204, content=b""),
        ]
    )
    try:
        client.webhooks.create({"url": "https://e.com", "eventTypes": ["email.sent"]})
        client.webhooks.list()
        client.webhooks.update("wh", {"enabled": False})
        client.webhooks.remove("wh")
    finally:
        http.close()
    assert json.loads(calls[0].content) == {"url": "https://e.com", "event_types": ["email.sent"]}
    assert calls[0].url.path == "/api/v1/webhook-endpoints"
    assert calls[3].method == "DELETE" and calls[3].url.path == "/api/v1/webhook-endpoints/wh"


def test_webhook_events_retry_alias_attribute():
    client, calls, http = make_sync([ok_data({"id": "ev", "webhook_status": "queued"})])
    try:
        assert client.webhook_events is client.webhookEvents
        result = client.webhookEvents.retry("ev_1")
    finally:
        http.close()
    assert result["webhook_status"] == "queued"
    assert calls[0].method == "POST" and calls[0].url.path == "/api/v1/events/ev_1/retry"


def test_suppressions_resource():
    client, calls, http = make_sync(
        [
            ok_data({"recipient": "bad@x.com", "reason": "manual"}),
            ok_data({"data": []}),
            httpx.Response(204, content=b""),
        ]
    )
    try:
        client.suppressions.add({"recipient": "bad@x.com", "reason": "manual"})
        client.suppressions.list()
        client.suppressions.remove("bad@x.com")
    finally:
        http.close()
    assert calls[0].url.path == "/api/v1/suppressions"
    assert calls[2].method == "DELETE" and calls[2].url.path == "/api/v1/suppressions/bad@x.com"


def test_attachments_upload_alias():
    client, calls, http = make_sync([ok_data({"attachment_id": "att_1"})])
    try:
        client.attachments.upload(
            {"filename": "i.pdf", "contentBase64": "QQ==", "contentType": "application/pdf"}
        )
    finally:
        http.close()
    assert json.loads(calls[0].content) == {
        "filename": "i.pdf",
        "content_base64": "QQ==",
        "content_type": "application/pdf",
    }


# --------------------------------------------------------------------------- #
# Raw request + options
# --------------------------------------------------------------------------- #


def test_raw_request_and_unwrap_data_false():
    client, calls, http = make_sync([ok_data({"id": "x"}), ok_data({"id": "x"})])
    try:
        unwrapped = client.request("GET", "/emails", RequestOptions(query={"limit": 5}))
        raw = client.request("GET", "/emails", RequestOptions(unwrap_data=False))
    finally:
        http.close()
    assert unwrapped == {"id": "x"}
    assert raw == {"ok": True, "data": {"id": "x"}}
    assert dict(calls[0].url.params) == {"limit": "5"}


def test_idempotency_and_header_merge_and_accept_override():
    client, calls, http = make_sync(
        [ok_data({}), ok_data({})],
        headers={"x-base": "1"},
    )
    try:
        client.emails.send(
            {"from": "a", "to": "b", "text": "x"},
            RequestOptions(
                headers={"x-req": "2", "accept": "application/xml"},
                idempotency_key="key-1",
            ),
        )
        client.emails.send({"from": "a", "to": "b", "text": "x"})
    finally:
        http.close()
    first = calls[0]
    assert first.headers["x-base"] == "1"
    assert first.headers["x-req"] == "2"
    assert first.headers["accept"] == "application/xml"  # not overwritten
    assert first.headers["idempotency-key"] == "key-1"
    assert "idempotency-key" not in calls[1].headers


def test_constructor_defaults_query_and_transform_and_middleware():
    seen: list[str] = []

    def mw(context, next_call):
        seen.append("mw")
        return next_call(context)

    client, calls, http = make_sync(
        [ok({"id": "z"})],
        query={"team": "t1"},
        middleware=[mw],
        transform_response=lambda ctx: {"wrapped": ctx.payload},
    )
    try:
        result = client.request("GET", "/emails")
    finally:
        http.close()
    assert result == {"wrapped": {"id": "z"}}
    assert seen == ["mw"]
    assert dict(calls[0].url.params) == {"team": "t1"}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


def test_authenticated_false_strips_authorization():
    client, calls, http = make_sync([ok_data({}), ok_data({})])
    try:
        # No pre-existing header: nothing to strip.
        client.request("GET", "/emails", RequestOptions(authenticated=False))
        # Pre-existing Authorization header is removed when authenticated=False.
        client.request(
            "GET",
            "/emails",
            RequestOptions(authenticated=False, headers={"authorization": "Bearer leak"}),
        )
    finally:
        http.close()
    assert "authorization" not in calls[0].headers
    assert "authorization" not in calls[1].headers


def test_missing_auth_raises():
    client, calls, http = make_sync([ok_data({})], token=None)
    try:
        with pytest.raises(TypeError, match="auth is required"):
            client.request("GET", "/emails")
    finally:
        http.close()
    assert calls == []


def test_explicit_authorization_header_allows_unauthenticated_client():
    client, calls, http = make_sync([ok_data({})], token=None)
    try:
        client.request("GET", "/emails", RequestOptions(headers={"authorization": "Bearer raw"}))
    finally:
        http.close()
    assert calls[0].headers["authorization"] == "Bearer raw"


def test_headers_auth_static_and_callable_and_bearer_callable():
    client, calls, http = make_sync(
        [ok_data({}), ok_data({}), ok_data({})],
        token=None,
        auth=HeadersAuthStrategy(headers={"x-api-key": "secret"}),
    )
    try:
        client.request("GET", "/emails")
        client.request(
            "GET",
            "/emails",
            RequestOptions(auth=HeadersAuthStrategy(headers=lambda ctx: {"x-dyn": ctx.method})),
        )
        client.request(
            "GET",
            "/emails",
            RequestOptions(auth=BearerAuthStrategy(token=lambda ctx: "dynamic")),
        )
    finally:
        http.close()
    assert calls[0].headers["x-api-key"] == "secret"
    assert calls[1].headers["x-dyn"] == "GET"
    assert calls[2].headers["authorization"] == "Bearer dynamic"


def test_auth_true_resolves_to_no_headers():
    client, calls, http = make_sync([ok_data({})], token=None, auth=True)
    try:
        client.request("GET", "/emails")
    finally:
        http.close()
    assert "authorization" not in calls[0].headers


# --------------------------------------------------------------------------- #
# Base URL handling
# --------------------------------------------------------------------------- #


def test_custom_base_url_and_absolute_path():
    client, calls, http = make_sync(
        [ok_data({}), ok_data({})],
        base_url="https://sendstack.norialabs.com/api/",
    )
    try:
        client.request("GET", "/emails")
        client.request("GET", "https://other.example.com/raw")
    finally:
        http.close()
    assert str(calls[0].url) == "https://sendstack.norialabs.com/api/emails"
    assert str(calls[1].url) == "https://other.example.com/raw"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def test_error_envelope_response_raises():
    client, calls, http = make_sync(
        [ok({"ok": False, "error": {"message": "nope", "code": "bad", "details": [1]}}, 400)]
    )
    try:
        with pytest.raises(SendstackError) as info:
            client.request("GET", "/emails")
    finally:
        http.close()
    err = info.value
    assert err.status_code == 400
    assert err.code == "bad"
    assert err.details == [1]


def test_no_retry_by_default_raises_on_500():
    client, calls, http = make_sync([ok({"message": "boom"}, 500)])
    try:
        with pytest.raises(SendstackError, match="boom"):
            client.request("GET", "/emails")
    finally:
        http.close()
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# Retry (sync)
# --------------------------------------------------------------------------- #


def test_retry_on_status_then_success():
    client, calls, http = make_sync(
        [httpx.Response(503, json={"detail": "busy"}), ok_data({"id": "ok"})],
        retry=RetryOptions(max_attempts=2, delay_seconds=0),
    )
    try:
        assert client.request("GET", "/emails") == {"id": "ok"}
    finally:
        http.close()
    assert len(calls) == 2


def test_retry_exhausted_raises():
    client, calls, http = make_sync(
        [httpx.Response(503), httpx.Response(503)],
        retry=2,
    )
    try:
        with pytest.raises(SendstackError) as info:
            client.request("GET", "/emails")
    finally:
        http.close()
    assert info.value.status_code == 503
    assert len(calls) == 2


def test_custom_should_retry_true_retries_non_default_status():
    client, calls, http = make_sync(
        [httpx.Response(400), ok_data({"id": "ok"})],
        retry=RetryOptions(max_attempts=2, delay_seconds=0, should_retry=lambda ctx: True),
    )
    try:
        assert client.request("GET", "/emails") == {"id": "ok"}
    finally:
        http.close()
    assert len(calls) == 2


def test_retry_on_exception_then_success():
    client, calls, http = make_sync(
        [httpx.ConnectError("down"), ok_data({"id": "ok"})],
        retry=RetryOptions(max_attempts=2, delay_seconds=0),
    )
    try:
        assert client.request("GET", "/emails") == {"id": "ok"}
    finally:
        http.close()
    assert len(calls) == 2


def test_retry_exception_exhausted_reraises():
    client, calls, http = make_sync(
        [httpx.ConnectError("a"), httpx.ConnectError("b")],
        retry=RetryOptions(max_attempts=2, delay_seconds=0),
    )
    try:
        with pytest.raises(httpx.ConnectError):
            client.request("GET", "/emails")
    finally:
        http.close()
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# Custom parse / transform / per-request overrides (sync)
# --------------------------------------------------------------------------- #


def test_custom_parse_and_transform_per_request():
    client, calls, http = make_sync(
        [httpx.Response(200, text="42", headers={"x-total": "7"})]
    )
    try:
        result = client.request(
            "GET",
            "/metrics",
            RequestOptions(
                parse_response=lambda response, ctx: response.headers["x-total"],
                transform_response=lambda ctx: {"total": int(ctx.payload)},
            ),
        )
    finally:
        http.close()
    assert result == {"total": 7}


def test_sync_parser_returning_awaitable_raises():
    client, calls, http = make_sync(
        [ok_data({})],
        parse_response=lambda response, ctx: _Awaitable(),
    )
    try:
        with pytest.raises(TypeError, match="awaitable in the synchronous"):
            client.request("GET", "/emails")
    finally:
        http.close()


def test_per_request_client_and_timeout_and_retry_override():
    base_calls: list[httpx.Request] = []
    base_http = httpx.Client(
        transport=httpx.MockTransport(_handler([ok_data({"v": "base"})], base_calls))
    )
    other_calls: list[httpx.Request] = []
    other_http = httpx.Client(
        transport=httpx.MockTransport(_handler([ok_data({"v": "other"})], other_calls))
    )
    client = Sendstack("tok", client=base_http)
    try:
        result = client.request(
            "GET",
            "/emails",
            RequestOptions(client=other_http, timeout_seconds=5.0, retry=False),
        )
    finally:
        base_http.close()
        other_http.close()
    assert result == {"v": "other"}
    assert base_calls == []
    assert other_calls[0].extensions["timeout"]["connect"] == 5.0


def test_close_owns_vs_injected_and_context_manager():
    injected = httpx.Client(transport=httpx.MockTransport(_handler([], [])))
    with Sendstack("tok", client=injected) as client:
        assert client._owns_client is False
    assert injected.is_closed is False  # injected client is left open
    injected.close()

    owned = Sendstack("tok")
    assert owned._owns_client is True
    owned.close()
    assert owned._client.is_closed is True


def test_default_base_url_when_unspecified():
    client = Sendstack("tok")
    try:
        assert client.base_url == "https://sendstack.norialabs.com/api/v1"
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# Async
# --------------------------------------------------------------------------- #


def test_async_send_and_context_manager():
    calls: list[httpx.Request] = []

    async def run():
        http = make_async_http([ok_data({"id": "a1", "status": "queued"})], calls)
        async with http, AsyncSendstack("tok", client=http) as client:
            assert client._owns_client is False
            return await client.emails.send({"from": "a", "to": "b", "text": "x"})

    result = run_async(run)
    assert result == {"id": "a1", "status": "queued"}
    assert calls[0].headers["authorization"] == "Bearer tok"


def test_async_owns_client_and_aclose():
    async def run():
        client = AsyncSendstack("tok")
        assert client._owns_client is True
        await client.aclose()
        return client._client.is_closed

    assert run_async(run) is True


def test_async_retry_status_and_exception_paths():
    status_calls: list[httpx.Request] = []
    exc_calls: list[httpx.Request] = []

    async def run():
        http1 = make_async_http(
            [httpx.Response(503), ok_data({"id": "ok"})], status_calls
        )
        http2 = make_async_http(
            [httpx.ConnectError("down"), ok_data({"id": "ok2"})], exc_calls
        )
        async with http1, http2:
            policy = RetryOptions(max_attempts=2, delay_seconds=0)
            c1 = AsyncSendstack("t", client=http1, retry=policy)
            c2 = AsyncSendstack("t", client=http2, retry=policy)
            r1 = await c1.request("GET", "/emails")
            r2 = await c2.request("GET", "/emails")
            return r1, r2

    r1, r2 = run_async(run)
    assert r1 == {"id": "ok"} and r2 == {"id": "ok2"}
    assert len(status_calls) == 2 and len(exc_calls) == 2


def test_async_exception_exhausted_reraises():
    async def run():
        http = make_async_http([httpx.ConnectError("a"), httpx.ConnectError("b")], [])
        async with http:
            policy = RetryOptions(max_attempts=2, delay_seconds=0)
            client = AsyncSendstack("t", client=http, retry=policy)
            with pytest.raises(httpx.ConnectError):
                await client.request("GET", "/emails")

    run_async(run)


def test_async_auth_variants_and_middleware_and_transform():
    calls: list[httpx.Request] = []
    seen: list[str] = []

    async def token_provider(ctx):
        return "atok"

    async def headers_provider(ctx):
        return {"x-h": "v"}

    async def mw(context, next_call):
        seen.append("mw")
        return await next_call(context)

    async def run():
        http = make_async_http([ok({"id": "1"}), ok_data({}), ok_data({}), ok_data({})], calls)
        async with http:
            bearer = AsyncSendstack(
                "ignored",
                client=http,
                auth=BearerAuthStrategy(token=token_provider),
                middleware=[mw],
                transform_response=lambda ctx: {"wrap": ctx.payload},
            )
            first = await bearer.request("GET", "/emails")
            hdr_auth = HeadersAuthStrategy(headers=headers_provider)
            hdr = AsyncSendstack("x", client=http, auth=hdr_auth)
            await hdr.request("GET", "/emails")
            true_auth = AsyncSendstack(None, client=http, auth=True)
            await true_auth.request("GET", "/emails")
            no_auth = AsyncSendstack(None, client=http)
            with pytest.raises(TypeError):
                await no_auth.request("GET", "/emails")
            return first

    first = run_async(run)
    assert first == {"wrap": {"id": "1"}}
    assert seen == ["mw"]
    assert calls[0].headers["authorization"] == "Bearer atok"
    assert calls[1].headers["x-h"] == "v"
    assert "authorization" not in calls[2].headers


def test_async_authenticated_false_and_async_parser():
    calls: list[httpx.Request] = []

    async def async_parser(response, ctx):
        return {"parsed": response.status_code}

    async def run():
        http = make_async_http([ok_data({}), httpx.Response(200, text="x")], calls)
        async with http:
            client = AsyncSendstack("tok", client=http)
            await client.request("GET", "/emails", RequestOptions(authenticated=False))
            options = RequestOptions(parse_response=async_parser)
            return await client.request("GET", "/emails", options)

    result = run_async(run)
    assert "authorization" not in calls[0].headers
    assert result == {"parsed": 200}


# --------------------------------------------------------------------------- #
# Error mapping unit tests
# --------------------------------------------------------------------------- #


def test_to_sendstack_error_branches():
    env = to_sendstack_error(
        400, {"ok": False, "error": {"message": "m", "code": "c", "details": 9}}
    )
    assert (env.message, env.code, env.details) == ("m", "c", 9)

    env_empty = to_sendstack_error(400, {"ok": False, "error": {}})
    assert "status 400" in env_empty.message

    detail = to_sendstack_error(422, {"detail": "bad", "errors": [1]})
    assert detail.message == "bad" and detail.details == [1]

    msg = to_sendstack_error(400, {"message": "mm", "code": "CODE", "details": 1})
    assert msg.code == "CODE"

    msg_noncode = to_sendstack_error(400, {"message": "mm", "code": 123})
    assert msg_noncode.message == "mm" and msg_noncode.code is None

    mapping_other = to_sendstack_error(500, {"foo": "bar"})
    assert "status 500" in mapping_other.message

    exc = to_sendstack_error(500, ValueError("boom"))
    assert exc.message == "boom"

    text = to_sendstack_error(500, "oops")
    assert text.message == "oops"

    blank = to_sendstack_error(500, "   ")
    assert "status 500" in blank.message

    none = to_sendstack_error(500, None)
    assert "status 500" in none.message


def test_envelope_predicates():
    assert is_error_envelope({"ok": False, "error": {}}) is True
    assert is_error_envelope({"ok": True}) is False
    assert is_error_envelope({"ok": False, "error": "x"}) is False
    assert is_error_envelope("x") is False
    assert is_success_envelope({"ok": True, "data": 1}) is True
    assert is_success_envelope({"ok": True}) is False
    assert is_success_envelope(5) is False


# --------------------------------------------------------------------------- #
# Retry / sleep helper unit tests
# --------------------------------------------------------------------------- #


def _ctx() -> SendstackRequestContext:
    return SendstackRequestContext(
        method="GET", path="/x", url="http://x/x", headers=httpx.Headers()
    )


def test_normalize_retry_policy():
    assert cm._normalize_retry_policy(None).max_attempts == 1
    assert cm._normalize_retry_policy(False).max_attempts == 1
    assert cm._normalize_retry_policy(True).max_attempts == 2
    assert cm._normalize_retry_policy(5).max_attempts == 5
    assert cm._normalize_retry_policy(0).max_attempts == 1
    copied = cm._normalize_retry_policy(RetryOptions(max_attempts=3, delay_seconds=1))
    assert copied.max_attempts == 3 and copied.delay_seconds == 1


def test_default_should_retry():
    def retry(**kwargs):
        return cm._default_should_retry(SendstackRetryContext(_ctx(), 1, **kwargs))

    assert retry(error=SendstackError("x", status_code=1)) is False
    assert retry(error=ValueError()) is True
    assert retry() is False
    assert retry(response=httpx.Response(503)) is True
    assert retry(response=httpx.Response(404)) is False


def test_default_retry_delay():
    assert cm._default_retry_delay(1) == pytest.approx(0.1)
    assert cm._default_retry_delay(10) == 1.0


def test_sync_retry_delay_and_should_retry():
    ctx = SendstackRetryContext(_ctx(), 1)
    assert cm._sync_retry_delay(RetryOptions(), ctx) == pytest.approx(0.1)
    assert cm._sync_retry_delay(RetryOptions(delay_seconds=lambda c: 0), ctx) == 0
    assert cm._sync_retry_delay(RetryOptions(delay_seconds=2), ctx) == 2.0
    assert cm._sync_should_retry(RetryOptions(should_retry=lambda c: True), ctx) is True


def test_async_retry_delay_and_should_retry():
    ctx = SendstackRetryContext(_ctx(), 1)

    async def run():
        a = await cm._async_retry_delay(RetryOptions(), ctx)
        b = await cm._async_retry_delay(RetryOptions(delay_seconds=lambda c: 0), ctx)
        c = await cm._async_retry_delay(RetryOptions(delay_seconds=2), ctx)
        d = await cm._async_should_retry(RetryOptions(should_retry=lambda c: True), ctx)
        e = await cm._async_should_retry(RetryOptions(), SendstackRetryContext(_ctx(), 1))
        return a, b, c, d, e

    a, b, c, d, e = run_async(run)
    assert a == pytest.approx(0.1) and b == 0 and c == 2.0 and d is True and e is False


def test_sleep_helpers(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(cm.time, "sleep", lambda s: slept.append(s))
    cm._sleep_seconds(0.5)
    cm._sleep_seconds(0)
    assert slept == [0.5]

    async_slept: list[float] = []

    async def fake_sleep(s):
        async_slept.append(s)

    monkeypatch.setattr(cm.asyncio, "sleep", fake_sleep)

    async def run():
        await cm._async_sleep_seconds(0.5)
        await cm._async_sleep_seconds(0)

    run_async(run)
    assert async_slept == [0.5]


def test_resolve_value_helpers():
    assert cm._resolve_sync_value(5, "x") == 5
    with pytest.raises(TypeError):
        cm._resolve_sync_value(_Awaitable(), "Parser")

    async def run():
        async def coro():
            return 9

        return await cm._resolve_async_value(coro()), await cm._resolve_async_value(3)

    assert run_async(run) == (9, 3)


def test_quote_and_explicit_auth_headers():
    assert cm._quote("a/b c") == "a%2Fb%20c"
    assert cm._has_explicit_auth_headers(httpx.Headers({"authorization": "x"})) is True
    assert cm._has_explicit_auth_headers(httpx.Headers()) is False


# --------------------------------------------------------------------------- #
# Utils unit tests
# --------------------------------------------------------------------------- #


def test_normalize_base_url():
    assert normalize_base_url("https://x.com/api/") == "https://x.com/api"
    with pytest.raises(TypeError, match="required"):
        normalize_base_url("  ")
    with pytest.raises(TypeError, match="absolute URL"):
        normalize_base_url("not-a-url")


def test_build_request_url():
    assert build_request_url("https://x.com", "/p") == "https://x.com/p"
    assert build_request_url("https://x.com", "http://y.com/z") == "http://y.com/z"


def test_serialize_datetime_variants():
    assert serialize_datetime(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00.000Z"
    assert serialize_datetime(datetime(2026, 1, 1)) == "2026-01-01T00:00:00.000"
    plus3 = serialize_datetime(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3))))
    assert plus3.endswith("+03:00")


def test_serialize_query_value():
    assert serialize_query_value(True) == "true"
    assert serialize_query_value(False) == "false"
    assert serialize_query_value(7) == "7"
    assert serialize_query_value(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00.000Z"


def test_merge_query_params():
    assert merge_query_params(None, {"a": 1, "b": None}) == {"a": 1}
    assert merge_query_params({}, None) is None


def test_append_and_normalize_query_pairs():
    assert append_query_params("http://x/p", None) == "http://x/p"
    merged = append_query_params("http://x/p?a=1&z=9", {"a": 2})
    assert "a=2" in merged and "z=9" in merged and "a=1" not in merged
    assert normalize_query_pairs(None) == []
    assert normalize_query_pairs({"a": None}) == []
    assert normalize_query_pairs({"a": [1, 2, None]}) == [("a", "1"), ("a", "2")]
    assert normalize_query_pairs({"a": 1}) == [("a", "1")]


def test_merge_headers():
    headers = merge_headers(None, {"a": "b"}, httpx.Headers({"c": "d"}))
    assert headers["a"] == "b" and headers["c"] == "d"


def test_parse_response_body():
    empty = httpx.Response(200, content=b"", headers={"content-type": "application/json"})
    assert parse_response_body(empty) is None
    assert parse_response_body(httpx.Response(200, json={"a": 1})) == {"a": 1}
    assert parse_response_body(
        httpx.Response(200, text='{"a":1}', headers={"content-type": "text/plain"})
    ) == {"a": 1}
    assert parse_response_body(
        httpx.Response(200, text="hello", headers={"content-type": "text/plain"})
    ) == "hello"


def test_prepare_request_body():
    from sendstack.types import UNSET

    assert prepare_request_body(UNSET, httpx.Headers()) is UNSET
    assert prepare_request_body(b"raw", httpx.Headers()) == b"raw"
    headers = httpx.Headers()
    assert prepare_request_body({"a": 1}, headers) == '{"a":1}'
    assert headers["content-type"] == "application/json"
    preset = httpx.Headers({"content-type": "application/custom"})
    prepare_request_body({"a": 1}, preset)
    assert preset["content-type"] == "application/custom"


def test_json_default_and_as_mapping():
    assert json_default(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00.000Z"
    with pytest.raises(TypeError):
        json_default(object())
    assert as_mapping({"a": 1}) == {"a": 1}
    assert as_mapping(5) == {}
