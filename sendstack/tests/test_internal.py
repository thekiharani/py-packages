from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

import sendstack.client as client_module
from sendstack import (
    AsyncMailer,
    HeadersAuthStrategy,
    Mailer,
    MailerError,
    RequestOptions,
    RetryOptions,
)
from sendstack.client import (
    _async_retry_delay,
    _async_should_retry,
    _async_sleep_seconds,
    _default_retry_delay,
    _default_should_retry,
    _normalize_retry_policy,
    _quote,
    _resolve_async_auth_headers,
    _resolve_sync_auth_headers,
    _sync_retry_delay,
    _sync_should_retry,
)
from sendstack.errors import error_envelope_message, is_error_envelope
from sendstack.types import (
    UNSET,
    BearerAuthStrategy,
    MailerRequestContext,
    MailerRetryContext,
)
from sendstack.utils import (
    as_mapping,
    build_request_url,
    json_default,
    normalize_base_url,
    normalize_query_pairs,
    parse_response_body,
    prepare_request_body,
    serialize_datetime,
    serialize_query_value,
)


def make_json_response(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        headers={"content-type": "application/json"},
    )


@dataclass(slots=True)
class FakeSyncRequester:
    actions: list[object]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.actions:
            raise AssertionError("No sync actions left.")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


@dataclass(slots=True)
class FakeAsyncRequester:
    actions: list[object]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.actions:
            raise AssertionError("No async actions left.")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    async def aclose(self) -> None:
        self.closed = True


class FakeAwaitable:
    def __await__(self):  # type: ignore[override]
        yield
        return "value"


def make_request_context(path: str = "/test") -> MailerRequestContext:
    return MailerRequestContext(
        method="GET",
        path=path,
        url=f"https://mailer.example.com{path}",
        headers=httpx.Headers(),
        body=UNSET,
        timeout_seconds=1.0,
        attempt=1,
    )


def test_utils_and_error_helpers_cover_edge_cases() -> None:
    with pytest.raises(TypeError, match="required"):
        normalize_base_url("   ")
    with pytest.raises(TypeError, match="valid absolute URL"):
        normalize_base_url("/mailer")

    normalized = normalize_base_url(" https://mailer.example.com/base/?region=eu#hash ")
    assert normalized == "https://mailer.example.com/base?region=eu"
    assert build_request_url("https://mailer.example.com/base", "https://alt.example.com/raw") == (
        "https://alt.example.com/raw"
    )

    east_africa = datetime(2026, 4, 13, 9, 30, tzinfo=timezone(timedelta(hours=3)))
    assert serialize_datetime(east_africa).endswith("+03:00")
    assert serialize_query_value(False) == "false"
    assert normalize_query_pairs(None) == []
    assert normalize_query_pairs(
        {
            "skip": None,
            "tag": ["welcome", None, "trial"],
            "since": east_africa,
            "flag": False,
        }
    ) == [
        ("tag", "welcome"),
        ("tag", "trial"),
        ("since", serialize_datetime(east_africa)),
        ("flag", "false"),
    ]

    assert parse_response_body(
        httpx.Response(
            status_code=200,
            text="   ",
            headers={"content-type": "text/plain"},
        )
    ) is None
    assert parse_response_body(
        httpx.Response(
            status_code=200,
            text='{"ok": true, "via": "text"}',
            headers={"content-type": "text/plain"},
        )
    ) == {"ok": True, "via": "text"}

    headers = httpx.Headers()
    assert prepare_request_body(b"native-body", headers) == b"native-body"
    assert headers.get("content-type") is None

    assert json_default(datetime(2026, 4, 13, tzinfo=UTC)) == "2026-04-13T00:00:00.000Z"
    with pytest.raises(TypeError, match="not JSON serializable"):
        json_default(object())

    assert as_mapping("nope") == {}
    assert is_error_envelope({"ok": False, "error": "bad"}) is False
    assert error_envelope_message({"ok": False, "error": "bad"}) == (None, None, None)
    assert error_envelope_message({"detail": "Conflict"}) == ("Conflict", None, None)
    assert error_envelope_message(
        {
            "detail": "Request validation failed",
            "errors": [{"field": "to", "message": "Email recipient is required"}],
        }
    ) == (
        "Request validation failed",
        None,
        [{"field": "to", "message": "Email recipient is required"}],
    )


def test_sync_resource_surface_retry_helpers_and_failure_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSyncRequester(
        actions=[
            make_json_response(500, {"ok": False, "error": {"code": "TEMP", "message": "retry"}}),
            make_json_response(200, {"ok": True, "data": {"status": "ok"}}),
            make_json_response(200, {"ok": True, "data": [{"id": "email_batch_1"}]}),
            make_json_response(200, {"object": "email", "id": "email/1"}),
            make_json_response(201, {"object": "domain", "id": "domain_1"}),
            make_json_response(200, {"object": "list", "has_more": False, "data": []}),
            make_json_response(200, {"object": "domain", "id": "domain/1", "status": "verified"}),
            make_json_response(200, {"object": "domain", "id": "domain/1"}),
            make_json_response(200, {"object": "domain", "id": "domain/1", "deleted": True}),
            make_json_response(200, {"ok": True, "data": [{"id": "key_1"}]}),
            make_json_response(200, {"ok": True, "data": {"id": "key/1"}}),
            make_json_response(200, {"ok": True, "data": {"revoked": True}}),
            make_json_response(201, {"ok": True, "data": {"id": "webhook_1"}}),
            make_json_response(200, {"ok": True, "data": [{"id": "webhook_1"}]}),
            make_json_response(200, {"ok": True, "data": {"deleted": True}}),
            make_json_response(200, {"ok": True, "data": {"status": "ok"}}),
            make_json_response(500, {"unexpected": True}),
        ]
    )
    mailer = Mailer(
        "mk_live_sync_secret",
        base_url="https://mailer.example.com/base",
        client=client,
        headers={"x-client": "default"},
    )

    retry_result = mailer.request(
        "GET",
        "/retry-sync",
        RequestOptions(
            retry=2,
            timeout_seconds=5.0,
        ),
    )
    assert retry_result == {"status": "ok"}
    assert client.calls[0]["timeout"] == 5.0

    batch_result = mailer.emails.send_batch(
        [{"from": "a@example.com", "to": "b@example.com", "subject": "A", "text": "A"}]
    )
    assert batch_result == [{"id": "email_batch_1"}]

    email = mailer.emails.get("email/1")
    assert email["id"] == "email/1"
    assert client.calls[3]["url"] == "https://mailer.example.com/base/emails/email%2F1"

    assert mailer.domains.create({"name": "example.com"})["id"] == "domain_1"
    assert mailer.domains.list() == {"object": "list", "has_more": False, "data": []}
    assert mailer.domains.get("domain/1")["status"] == "verified"
    assert mailer.domains.verify("domain/1") == {"object": "domain", "id": "domain/1"}
    assert mailer.domains.remove("domain/1")["deleted"] is True

    assert mailer.api_keys.list()[0]["id"] == "key_1"
    assert mailer.api_keys.get("key/1")["id"] == "key/1"
    assert mailer.apiKeys.remove("key/1") == {"revoked": True}

    assert (
        mailer.webhooks.create({"url": "https://example.com", "events": ["email.sent"]})["id"]
        == "webhook_1"
    )
    assert mailer.webhooks.list()[0]["id"] == "webhook_1"
    assert mailer.webhooks.remove("webhook/1") == {"deleted": True}

    assert mailer.health.ready() == {"status": "ok"}

    with pytest.raises(MailerError, match="status 500"):
        mailer.request("GET", "/object-error")

    assert _normalize_retry_policy(True).max_attempts == 2
    assert _normalize_retry_policy(3).max_attempts == 3
    retry_context = MailerRetryContext(request=make_request_context(), attempt=1)
    assert _default_should_retry(retry_context) is False
    assert _default_should_retry(
        MailerRetryContext(
            request=make_request_context(),
            attempt=1,
            error=RuntimeError("boom"),
        )
    ) is True
    assert _default_retry_delay(4) == 0.8
    assert _sync_should_retry(
        RetryOptions(should_retry=lambda _context: True),
        MailerRetryContext(request=make_request_context(), attempt=1),
    )
    assert _sync_retry_delay(
        RetryOptions(),
        MailerRetryContext(request=make_request_context(), attempt=1),
    ) == 0.1
    assert _sync_retry_delay(
        RetryOptions(delay_seconds=lambda _context: 0.25),
        MailerRetryContext(request=make_request_context(), attempt=1),
    ) == 0.25
    assert _resolve_sync_auth_headers(False, make_request_context()) == httpx.Headers()
    assert _quote("folder/value one") == "folder%2Fvalue%20one"

    with pytest.raises(TypeError, match="auth is required"):
        Mailer(
            "",
            base_url="https://mailer.example.com",
            client=FakeSyncRequester(actions=[]),
        ).request("GET", "/needs-auth")

    with pytest.raises(TypeError, match="awaitable"):
        Mailer(
            "",
            base_url="https://mailer.example.com",
            client=FakeSyncRequester(actions=[]),
            auth=BearerAuthStrategy(token=lambda _context: FakeAwaitable()),
        ).request("GET", "/awaitable-auth")

    monkeypatch.setattr(
        client_module,
        "_normalize_retry_policy",
        lambda _retry: RetryOptions(max_attempts=0),
    )
    with pytest.raises(MailerError, match="exhausted"):
        mailer.request("GET", "/never-runs")


def test_async_resource_surface_retry_helpers_and_failure_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async with AsyncMailer("mk_live_owned_secret", base_url="https://mailer.example.com"):
            pass

        client = FakeAsyncRequester(
            actions=[
                make_json_response(200, {"ok": True, "data": {"ok": True}}),
                make_json_response(200, {"id": "email_1"}),
                make_json_response(200, {"ok": True, "data": [{"id": "email_batch_1"}]}),
                make_json_response(200, {"object": "email", "id": "email/async"}),
                make_json_response(200, {"object": "list", "has_more": False, "data": []}),
                make_json_response(201, {"object": "domain", "id": "domain_async"}),
                make_json_response(200, {"object": "list", "has_more": False, "data": []}),
                make_json_response(
                    200,
                    {"object": "domain", "id": "domain/async", "status": "verified"},
                ),
                make_json_response(200, {"object": "domain", "id": "domain/async"}),
                make_json_response(
                    200,
                    {"object": "domain", "id": "domain/async", "deleted": True},
                ),
                make_json_response(200, {"ok": True, "data": {"id": "key_async"}}),
                make_json_response(200, {"ok": True, "data": [{"id": "key_async"}]}),
                make_json_response(200, {"ok": True, "data": {"id": "key/async"}}),
                make_json_response(200, {"ok": True, "data": {"revoked": True}}),
                make_json_response(201, {"ok": True, "data": {"id": "webhook_async"}}),
                make_json_response(200, {"ok": True, "data": [{"id": "webhook_async"}]}),
                make_json_response(200, {"ok": True, "data": {"deleted": True}}),
                make_json_response(200, {"ok": True, "data": {"status": "ok"}}),
                make_json_response(200, {"ok": True, "data": {"status": "ok"}}),
            ]
        )
        mailer = AsyncMailer(
            "",
            base_url="https://mailer.example.com/base",
            client=client,
            headers={"authorization": "Bearer inherited", "x-client": "default"},
            auth=HeadersAuthStrategy(headers=lambda context: _async_headers(context.path)),
        )

        raw = await mailer.request("GET", "/headers-auth")
        assert raw == {"ok": True}
        assert client.calls[0]["headers"].get("x-auth-path") == "/headers-auth"

        send_result = await mailer.emails.send(
            {
                "from": "a@example.com",
                "to": "b@example.com",
                "subject": "Hello",
                "text": "World",
            },
            RequestOptions(idempotency_key="async-send-1"),
        )
        assert send_result == {"id": "email_1"}
        assert client.calls[1]["headers"].get("idempotency-key") == "async-send-1"

        assert await mailer.emails.send_batch(
            [{"from": "a@example.com", "to": "b@example.com", "subject": "A", "text": "A"}]
        ) == [{"id": "email_batch_1"}]
        assert (await mailer.emails.get("email/async"))["id"] == "email/async"
        assert await mailer.emails.list(limit=1) == {
            "object": "list",
            "has_more": False,
            "data": [],
        }

        assert (await mailer.domains.create({"name": "example.com"}))["id"] == "domain_async"
        assert await mailer.domains.list() == {"object": "list", "has_more": False, "data": []}
        assert (await mailer.domains.get("domain/async"))["status"] == "verified"
        assert await mailer.domains.verify("domain/async") == {
            "object": "domain",
            "id": "domain/async",
        }
        assert (await mailer.domains.remove("domain/async"))["deleted"] is True

        assert (await mailer.api_keys.create())["id"] == "key_async"
        assert (await mailer.apiKeys.list())[0]["id"] == "key_async"
        assert (await mailer.api_keys.get("key/async"))["id"] == "key/async"
        assert await mailer.api_keys.remove("key/async") == {"revoked": True}

        assert (
            await mailer.webhooks.create(
                {"url": "https://example.com", "events": ["email.sent"]}
            )
        )["id"] == "webhook_async"
        assert (await mailer.webhooks.list())[0]["id"] == "webhook_async"
        assert await mailer.webhooks.remove("webhook/async") == {"deleted": True}

        assert await mailer.health.check() == {"status": "ok"}
        assert client.calls[17]["headers"].get("authorization") is None
        assert await mailer.health.ready() == {"status": "ok"}

        retry_client = FakeAsyncRequester(
            actions=[
                httpx.ConnectError("temporary failure"),
                make_json_response(200, {"ok": True, "data": {"recovered": True}}),
            ]
        )
        retry_mailer = AsyncMailer(
            "mk_live_async_secret",
            base_url="https://mailer.example.com",
            client=retry_client,
        )
        retry_result = await retry_mailer.request(
            "GET",
            "/retry-exception",
            RequestOptions(retry=RetryOptions(max_attempts=2, delay_seconds=0)),
        )
        assert retry_result == {"recovered": True}
        assert len(retry_client.calls) == 2

        with pytest.raises(TypeError, match="auth is required"):
            await AsyncMailer(
                "",
                base_url="https://mailer.example.com",
                client=FakeAsyncRequester(actions=[]),
            ).request("GET", "/needs-auth")

        with pytest.raises(httpx.ConnectError):
            await AsyncMailer(
                "mk_live_async_secret",
                base_url="https://mailer.example.com",
                client=FakeAsyncRequester(actions=[httpx.ConnectError("stop")]),
            ).request("GET", "/stop")

        assert await _async_should_retry(
            RetryOptions(),
            MailerRetryContext(
                request=make_request_context(),
                attempt=1,
                response=make_json_response(500, {"ok": False}),
            ),
        )
        assert await _async_retry_delay(
            RetryOptions(),
            MailerRetryContext(request=make_request_context(), attempt=1),
        ) == 0.1
        assert await _async_retry_delay(
            RetryOptions(delay_seconds=2),
            MailerRetryContext(request=make_request_context(), attempt=1),
        ) == 2.0
        await _async_sleep_seconds(0.001)
        assert await _resolve_async_auth_headers(False, make_request_context()) == httpx.Headers()

        monkeypatch.setattr(
            client_module,
            "_normalize_retry_policy",
            lambda _retry: RetryOptions(max_attempts=0),
        )
        with pytest.raises(MailerError, match="exhausted"):
            await mailer.request("GET", "/never-runs")

    asyncio.run(scenario())


async def _async_headers(path: str) -> dict[str, str]:
    return {"x-auth-path": path}
