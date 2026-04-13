from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from sendstack import (
    AsyncMailer,
    BearerAuthStrategy,
    HeadersAuthStrategy,
    Mailer,
    MailerError,
    RequestOptions,
    RetryOptions,
)


def make_json_response(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        headers={"content-type": "application/json"},
    )


def make_text_response(status_code: int, text: str) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        text=text,
        headers={"content-type": "text/plain"},
    )


@dataclass(slots=True)
class FakeSyncRequester:
    actions: list[object]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.actions:
            raise AssertionError("No sync actions left.")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    def close(self) -> None:
        self.closed = True


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


def test_emails_send_sends_expected_request_and_uses_aliases() -> None:
    client = FakeSyncRequester(actions=[make_json_response(200, {"id": "email_123"})])
    mailer = Mailer(
        "sk_live_123_secret",
        base_url="https://sendstack.example.com/api/v1/",
        client=client,
    )

    result = mailer.emails.send(
        {
            "from": "Noria Demo <mail@noria.co.ke>",
            "to": ["hello@example.com"],
            "cc": "team@example.com",
            "subject": "Hello",
            "text": "World",
            "reply_to": ["support@noria.co.ke", "ops@noria.co.ke"],
            "configuration_set_name": "transactional",
            "tenant_name": "acme",
            "endpoint_id": "endpoint_123",
            "feedback_forwarding_email_address": "feedback@noria.co.ke",
            "feedback_forwarding_email_address_identity_arn": "arn:aws:ses:feedback",
            "from_email_address_identity_arn": "arn:aws:ses:from",
            "list_management_options": {
                "contact_list_name": "customers",
                "topic_name": "billing",
            },
            "attachments": [
                {
                    "filename": "invoice.txt",
                    "content_type": "text/plain",
                    "content": "aGVsbG8=",
                    "content_disposition": "inline",
                    "content_id": "cid-invoice",
                }
            ],
            "scheduled_at": "2026-03-28T09:00:00.000Z",
        },
        RequestOptions(idempotency_key="send-1"),
    )

    assert result == {"id": "email_123"}
    assert client.calls[0]["method"] == "POST"
    assert client.calls[0]["url"] == "https://sendstack.example.com/api/v1/emails"
    assert client.calls[0]["headers"].get("x-api-key") == "sk_live_123_secret"
    assert client.calls[0]["headers"].get("idempotency-key") == "send-1"
    assert client.calls[0]["headers"].get("content-type") == "application/json"
    assert json.loads(client.calls[0]["content"]) == {
        "from": "Noria Demo <mail@noria.co.ke>",
        "to": ["hello@example.com"],
        "cc": "team@example.com",
        "subject": "Hello",
        "text": "World",
        "replyTo": ["support@noria.co.ke", "ops@noria.co.ke"],
        "configurationSetName": "transactional",
        "tenantName": "acme",
        "endpointId": "endpoint_123",
        "feedbackForwardingEmailAddress": "feedback@noria.co.ke",
        "feedbackForwardingEmailAddressIdentityArn": "arn:aws:ses:feedback",
        "fromEmailAddressIdentityArn": "arn:aws:ses:from",
        "listManagementOptions": {
            "contactListName": "customers",
            "topicName": "billing",
        },
        "attachments": [
            {
                "filename": "invoice.txt",
                "contentType": "text/plain",
                "content": "aGVsbG8=",
                "disposition": "inline",
                "contentId": "cid-invoice",
            }
        ],
        "scheduledAt": "2026-03-28T09:00:00.000Z",
    }


def test_emails_list_encodes_query_params_and_preserves_base_path() -> None:
    client = FakeSyncRequester(
        actions=[make_json_response(200, {"object": "list", "has_more": False, "data": []})]
    )
    mailer = Mailer(
        "mk_live_123_secret",
        base_url="https://gateway.example.com/mailer-api",
        client=client,
    )

    result = mailer.emails.list(cursor="cursor_50", per_page=25, status="sent")

    assert result == {"object": "list", "has_more": False, "data": []}
    assert (
        client.calls[0]["url"]
        == "https://gateway.example.com/mailer-api/emails?cursor=cursor_50&per_page=25&status=sent"
    )


def test_health_is_unauthenticated_and_strips_inherited_authorization_header() -> None:
    client = FakeSyncRequester(
        actions=[make_json_response(200, {"ok": True, "data": {"status": "ok"}})]
    )
    mailer = Mailer(
        "mk_live_123_secret",
        base_url="https://mailer.example.com",
        client=client,
        headers={"authorization": "Bearer inherited", "x-client": "default"},
    )

    result = mailer.health.check()

    assert result == {"status": "ok"}
    assert client.calls[0]["headers"].get("authorization") is None
    assert client.calls[0]["headers"].get("x-api-key") is None
    assert client.calls[0]["headers"].get("x-client") == "default"


def test_request_supports_auth_strategies_middleware_and_client_override() -> None:
    default_client = FakeSyncRequester(actions=[])
    override_client = FakeSyncRequester(
        actions=[make_json_response(200, {"ok": True, "data": {"ok": True}})]
    )
    mailer = Mailer(
        "",
        base_url="https://mailer.example.com",
        client=default_client,
        auth=HeadersAuthStrategy(headers=lambda context: {"x-auth-path": context.path}),
        headers={"x-client": "default"},
        middleware=[
            lambda context, next_call: (
                context.headers.__setitem__("x-middleware", "outer")
                or setattr(context, "url", f"{context.url}?via=middleware")
                or next_call(context)
            )
        ],
    )

    result = mailer.request(
        "GET",
        "/custom",
        RequestOptions(
            client=override_client,
            middleware=[
                lambda context, next_call: (
                    context.headers.__setitem__("x-inner", "true") or next_call(context)
                )
            ],
        ),
    )

    assert result == {"ok": True}
    assert default_client.calls == []
    assert override_client.calls[0]["url"] == "https://mailer.example.com/custom?via=middleware"
    assert override_client.calls[0]["headers"].get("x-auth-path") == "/custom"
    assert override_client.calls[0]["headers"].get("x-middleware") == "outer"
    assert override_client.calls[0]["headers"].get("x-inner") == "true"
    assert override_client.calls[0]["headers"].get("x-client") == "default"


def test_request_supports_sync_bearer_auth_compatibility() -> None:
    client = FakeSyncRequester(actions=[make_json_response(200, {"id": "compat_1"})])
    mailer = Mailer(
        base_url="https://compat.example.com/mailer",
        client=client,
        auth=BearerAuthStrategy(
            token=lambda context: f"compat-token:{context.path}",
            header_name="authorization",
            prefix="Bearer",
        ),
    )

    result = mailer.request("GET", "/compat")

    assert result == {"id": "compat_1"}
    assert client.calls[0]["headers"].get("authorization") == "Bearer compat-token:/compat"


def test_request_allows_caller_supplied_x_api_key_headers() -> None:
    client = FakeSyncRequester(
        actions=[make_json_response(200, {"ok": True, "data": {"ok": True}})]
    )
    mailer = Mailer(
        base_url="https://sendstack.example.com/api/v1",
        client=client,
    )

    result = mailer.request(
        "GET",
        "/emails",
        RequestOptions(
            auth=False,
            headers={"x-api-key": "sk_manual"},
        ),
    )

    assert result == {"ok": True}
    assert client.calls[0]["headers"].get("x-api-key") == "sk_manual"


def test_api_keys_create_unwraps_envelopes_and_serializes_expiry_alias() -> None:
    client = FakeSyncRequester(
        actions=[
            make_json_response(
                200,
                {
                    "ok": True,
                    "data": {
                        "id": "key_1",
                        "environment": "sandbox",
                        "keyPrefix": "mk_sandbox_1",
                    },
                },
            )
        ]
    )
    mailer = Mailer("mk_live_123_secret", base_url="https://mailer.example.com", client=client)

    result = mailer.api_keys.create(
        {
            "environment": "sandbox",
            "expires_at": datetime(2026, 3, 26, tzinfo=UTC),
        }
    )

    assert result["environment"] == "sandbox"
    payload = json.loads(client.calls[0]["content"])
    assert payload == {
        "environment": "sandbox",
        "expiresAt": "2026-03-26T00:00:00.000Z",
    }


def test_request_supports_custom_parser_transform_and_retry() -> None:
    client = FakeSyncRequester(
        actions=[
            httpx.ReadTimeout("temporary network issue"),
            httpx.Response(status_code=202, text="", headers={"x-total": "7"}),
        ]
    )
    mailer = Mailer(
        "mk_live_123_secret",
        base_url="https://mailer.example.com",
        client=client,
    )

    result = mailer.request(
        "GET",
        "/metrics",
        RequestOptions(
            retry=RetryOptions(max_attempts=2, delay_seconds=0),
            parse_response=lambda response, _context: response.headers.get("x-total"),
            transform_response=lambda context: {
                "total": int(context.payload),
                "status": context.response.status_code,
            },
        ),
    )

    assert result == {"total": 7, "status": 202}
    assert len(client.calls) == 2


def test_request_raises_mailer_error_for_structured_and_text_errors() -> None:
    structured_client = FakeSyncRequester(
        actions=[
            make_json_response(
                409,
                {
                    "ok": False,
                    "error": {
                        "code": "IDEMPOTENCY_KEY_REUSED",
                        "message": "Idempotency key has already been used for a different request.",
                        "details": {"field": "idempotency-key"},
                    },
                },
            )
        ]
    )
    structured_mailer = Mailer(
        "mk_live_123_secret",
        base_url="https://mailer.example.com",
        client=structured_client,
    )

    with pytest.raises(MailerError) as structured_exc:
        structured_mailer.emails.send(
            {
                "from": "a@example.com",
                "to": "b@example.com",
                "subject": "s",
                "text": "x",
            }
        )

    assert structured_exc.value.status_code == 409
    assert structured_exc.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert structured_exc.value.details == {"field": "idempotency-key"}

    text_client = FakeSyncRequester(actions=[make_text_response(502, "upstream exploded")])
    text_mailer = Mailer(
        "mk_live_123_secret",
        base_url="https://mailer.example.com",
        client=text_client,
    )

    with pytest.raises(MailerError, match="upstream exploded"):
        text_mailer.health.ready(RequestOptions(authenticated=False))


def test_sendstack_email_routes_support_x_api_key_auth_and_fastapi_errors() -> None:
    client = FakeSyncRequester(
        actions=[
            make_json_response(
                200,
                {
                    "channel": "email",
                    "estimated_units": 2,
                    "available_units": 98,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "email_v1"},
                },
            ),
            make_json_response(
                202,
                {
                    "id": "message_1",
                    "status": "queued",
                    "channel": "email",
                    "to_address": "recipient@example.com",
                },
            ),
            make_json_response(
                200,
                {
                    "items": [{"id": "message_1", "status": "queued"}],
                    "next_cursor": None,
                    "has_more": False,
                    "limit": 10,
                },
            ),
            make_json_response(
                409,
                {"detail": "Idempotency-Key reuse with a different request is not allowed"},
            ),
        ]
    )
    mailer = Mailer(
        "sk_test",
        base_url="https://sendstack.example.com/api/v1",
        client=client,
    )

    quote = mailer.emails.quote(
        {
            "from": "sender@example.com",
            "to": ["recipient@example.com"],
            "cc": "cc@example.com",
            "subject": "Quoted email",
            "text": "Quoted email",
            "reply_to": ["support@example.com", "help@example.com"],
        }
    )
    send = mailer.emails.send(
        {
            "from": "sender@example.com",
            "to": ["recipient@example.com"],
            "subject": "Queued email",
            "text": "Queued email",
            "reply_to": ["support@example.com", "help@example.com"],
        },
        RequestOptions(idempotency_key="sendstack-send-1"),
    )
    listing = mailer.emails.list(limit=10, status="queued")

    assert quote["estimated_units"] == 2
    assert send["status"] == "queued"
    assert listing["items"][0]["id"] == "message_1"
    assert client.calls[0]["url"] == "https://sendstack.example.com/api/v1/emails/quote"
    assert client.calls[0]["headers"].get("x-api-key") == "sk_test"
    assert client.calls[0]["headers"].get("authorization") is None
    assert json.loads(client.calls[0]["content"]) == {
        "from": "sender@example.com",
        "to": ["recipient@example.com"],
        "cc": "cc@example.com",
        "subject": "Quoted email",
        "text": "Quoted email",
        "replyTo": ["support@example.com", "help@example.com"],
    }
    assert client.calls[1]["url"] == "https://sendstack.example.com/api/v1/emails"
    assert client.calls[1]["headers"].get("idempotency-key") == "sendstack-send-1"
    assert client.calls[2]["url"] == "https://sendstack.example.com/api/v1/emails?limit=10&status=queued"

    with pytest.raises(
        MailerError,
        match="Idempotency-Key reuse with a different request is not allowed",
    ):
        mailer.emails.send(
            {
                "from": "sender@example.com",
                "to": "recipient@example.com",
                "subject": "Queued email",
                "text": "Queued email",
            },
            RequestOptions(idempotency_key="sendstack-send-1"),
        )


def test_sendstack_sms_whatsapp_and_health_resources() -> None:
    client = FakeSyncRequester(
        actions=[
            make_json_response(
                200,
                {
                    "channel": "sms",
                    "estimated_units": 2,
                    "available_units": 20,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "sms_v1"},
                },
            ),
            make_json_response(202, {"id": "sms_1", "channel": "sms", "status": "queued"}),
            make_json_response(
                200,
                {
                    "items": [{"id": "sms_1", "channel": "sms"}],
                    "next_cursor": None,
                    "has_more": False,
                    "limit": 5,
                },
            ),
            make_json_response(200, {"id": "sms_1", "channel": "sms", "status": "queued"}),
            make_json_response(
                200,
                {
                    "channel": "whatsapp",
                    "estimated_units": 1,
                    "available_units": 20,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "whatsapp_v1"},
                },
            ),
            make_json_response(202, {"id": "wa_1", "channel": "whatsapp", "status": "queued"}),
            make_json_response(
                200,
                {
                    "items": [{"id": "wa_1", "channel": "whatsapp"}],
                    "next_cursor": None,
                    "has_more": False,
                    "limit": 5,
                },
            ),
            make_json_response(200, {"id": "wa_1", "channel": "whatsapp", "status": "queued"}),
            make_json_response(200, {"status": "alive", "uptime_s": 12.3}),
        ]
    )
    mailer = Mailer(
        "sk_test",
        base_url="https://sendstack.example.com/api/v1",
        client=client,
    )

    sms_quote = mailer.sms.quote(
        {
            "from": "SENDSTACK",
            "to": "+254722111222",
            "text": "Quoted SMS",
        }
    )
    sms_send = mailer.sms.send(
        {
            "from": "SENDSTACK",
            "to": "+254722111222",
            "text": "Queued SMS",
        }
    )
    sms_list = mailer.sms.list(limit=5, status="queued")
    sms_get = mailer.sms.get("sms_1")

    whatsapp_quote = mailer.whatsapp.quote(
        {
            "from": "WABA",
            "to": "+254733000333",
            "text": "Quoted WhatsApp",
            "template_variables": {"first_name": "Mercy"},
        }
    )
    whatsapp_send = mailer.whatsapp.send(
        {
            "from": "WABA",
            "to": "+254733000333",
            "text": "Queued WhatsApp",
            "template_variables": {"first_name": "Mercy"},
        }
    )
    whatsapp_list = mailer.whatsapp.list(limit=5, status="queued")
    whatsapp_get = mailer.whatsapp.get("wa_1")
    live = mailer.health.live()

    assert sms_quote["channel"] == "sms"
    assert sms_send["id"] == "sms_1"
    assert sms_list["items"][0]["id"] == "sms_1"
    assert sms_get["channel"] == "sms"
    assert whatsapp_quote["channel"] == "whatsapp"
    assert whatsapp_send["id"] == "wa_1"
    assert whatsapp_list["items"][0]["id"] == "wa_1"
    assert whatsapp_get["channel"] == "whatsapp"
    assert live["status"] == "alive"
    assert client.calls[0]["url"] == "https://sendstack.example.com/api/v1/sms/quote"
    assert client.calls[2]["url"] == "https://sendstack.example.com/api/v1/sms?limit=5&status=queued"
    assert client.calls[4]["url"] == "https://sendstack.example.com/api/v1/whatsapp/messages/quote"
    assert json.loads(client.calls[4]["content"]) == {
        "from": "WABA",
        "to": "+254733000333",
        "text": "Quoted WhatsApp",
        "variables": {"first_name": "Mercy"},
    }
    assert client.calls[8]["url"] == "https://sendstack.example.com/livez"
    assert client.calls[8]["headers"].get("x-api-key") is None


def test_sendstack_merchant_resources_support_control_plane_routes() -> None:
    client = FakeSyncRequester(
        actions=[
            make_json_response(
                200,
                {
                    "items": [{"id": "message_merchant_1", "channel": "email"}],
                    "next_cursor": None,
                    "has_more": False,
                    "limit": 10,
                },
            ),
            make_json_response(200, {"id": "message_merchant_1", "channel": "email"}),
            make_json_response(
                200,
                {
                    "channel": "email",
                    "estimated_units": 1,
                    "available_units": 40,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "email_v1"},
                },
            ),
            make_json_response(
                200,
                {
                    "channel": "email",
                    "estimated_units": 3,
                    "available_units": 40,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "email_v1", "delivery_mode": "group"},
                },
            ),
            make_json_response(
                202,
                {"id": "merchant_email_1", "channel": "email", "status": "queued"},
            ),
            make_json_response(
                202,
                {
                    "messages": [{"id": "merchant_email_2"}, {"id": "merchant_email_3"}],
                    "recipient_count": 2,
                    "delivery_mode": "group",
                },
            ),
            make_json_response(
                200,
                {
                    "channel": "sms",
                    "estimated_units": 2,
                    "available_units": 40,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "sms_v1"},
                },
            ),
            make_json_response(202, {"id": "merchant_sms_1", "channel": "sms", "status": "queued"}),
            make_json_response(
                200,
                {
                    "channel": "whatsapp",
                    "estimated_units": 1,
                    "available_units": 40,
                    "reserved_units": 0,
                    "can_send": True,
                    "pricing": {"pricing_model": "whatsapp_v1"},
                },
            ),
            make_json_response(
                202,
                {"id": "merchant_wa_1", "channel": "whatsapp", "status": "queued"},
            ),
        ]
    )
    mailer = Mailer(
        base_url="https://sendstack.example.com/api/v1",
        client=client,
        auth=BearerAuthStrategy(token="merchant-token"),
    )

    listing = mailer.merchant.messages.list(
        "merchant_123",
        per_page=10,
        channel="email",
        status="queued",
    )
    message = mailer.merchant.messages.get("merchant_123", "message_merchant_1")
    quote = mailer.merchant.emails.quote(
        "merchant_123",
        {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Merchant email",
            "text": "Merchant email",
        },
    )
    group_quote = mailer.merchant.emails.quoteGroup(
        "merchant_123",
        {
            "from": "sender@example.com",
            "to": ["one@example.com", "two@example.com"],
            "cc": "cc@example.com",
            "subject": "Group quote",
            "text": "Group quote",
            "reply_to": ["support@example.com", "ops@example.com"],
        },
    )
    send = mailer.merchant.emails.send(
        "merchant_123",
        {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Merchant email",
            "text": "Queued merchant email",
        },
    )
    group_send = mailer.merchant.emails.sendGroup(
        "merchant_123",
        {
            "from": "sender@example.com",
            "to": ["one@example.com", "two@example.com"],
            "subject": "Group send",
            "text": "Queued group email",
            "reply_to": ["support@example.com", "ops@example.com"],
        },
        RequestOptions(idempotency_key="merchant-group-1"),
    )
    sms_quote = mailer.merchant.sms.quote(
        "merchant_123",
        {
            "from": "SENDSTACK",
            "to": "+254722111222",
            "text": "Merchant SMS",
        },
    )
    sms_send = mailer.merchant.sms.send(
        "merchant_123",
        {
            "from": "SENDSTACK",
            "to": "+254722111222",
            "text": "Queued merchant SMS",
        },
    )
    whatsapp_quote = mailer.merchant.whatsapp.quote(
        "merchant_123",
        {
            "from": "WABA",
            "to": "+254733000333",
            "text": "Merchant WhatsApp",
            "template_variables": {"first_name": "Mercy"},
        },
    )
    whatsapp_send = mailer.merchant.whatsapp.send(
        "merchant_123",
        {
            "from": "WABA",
            "to": "+254733000333",
            "text": "Queued merchant WhatsApp",
            "template_variables": {"first_name": "Mercy"},
        },
    )

    assert listing["items"][0]["id"] == "message_merchant_1"
    assert message["id"] == "message_merchant_1"
    assert quote["channel"] == "email"
    assert group_quote["pricing"]["delivery_mode"] == "group"
    assert send["id"] == "merchant_email_1"
    assert group_send["recipient_count"] == 2
    assert sms_quote["channel"] == "sms"
    assert sms_send["id"] == "merchant_sms_1"
    assert whatsapp_quote["channel"] == "whatsapp"
    assert whatsapp_send["id"] == "merchant_wa_1"
    assert (
        client.calls[0]["url"]
        == "https://sendstack.example.com/api/v1/merchants/merchant_123/messages?per_page=10&channel=email&status=queued"
    )
    assert client.calls[0]["headers"].get("authorization") == "Bearer merchant-token"
    assert client.calls[1]["url"] == (
        "https://sendstack.example.com/api/v1/merchants/merchant_123/messages/message_merchant_1"
    )
    assert client.calls[3]["url"] == (
        "https://sendstack.example.com/api/v1/merchants/merchant_123/messages/email/group/quote"
    )
    assert json.loads(client.calls[3]["content"]) == {
        "from": "sender@example.com",
        "to": ["one@example.com", "two@example.com"],
        "cc": "cc@example.com",
        "subject": "Group quote",
        "text": "Group quote",
        "replyTo": ["support@example.com", "ops@example.com"],
    }
    assert client.calls[5]["url"] == (
        "https://sendstack.example.com/api/v1/merchants/merchant_123/messages/email/group"
    )
    assert client.calls[5]["headers"].get("idempotency-key") == "merchant-group-1"
    assert json.loads(client.calls[8]["content"]) == {
        "from": "WABA",
        "to": "+254733000333",
        "text": "Merchant WhatsApp",
        "variables": {"first_name": "Mercy"},
    }


def test_send_batch_handles_array_and_passthrough_payloads() -> None:
    client = FakeSyncRequester(
        actions=[
            make_json_response(200, [{"id": "email_1"}]),
            make_json_response(200, {"ok": True, "data": {"notice": "not-an-array"}}),
        ]
    )
    mailer = Mailer(
        "mk_live_123_secret",
        base_url="https://mailer.example.com",
        client=client,
    )

    assert mailer.emails.send_batch(
        [{"from": "a@example.com", "to": "b@example.com", "subject": "A", "text": "A"}]
    ) == [{"id": "email_1"}]
    assert mailer.emails.send_batch(
        [{"from": "a@example.com", "to": "c@example.com", "subject": "B", "text": "B"}]
    ) == {"ok": True, "data": {"notice": "not-an-array"}}


def test_sync_mailer_context_manager_closes_owned_client() -> None:
    with Mailer("mk_live_123_secret", base_url="https://mailer.example.com") as mailer:
        assert mailer.api_key == "mk_live_123_secret"
    assert mailer._owns_client is True


def test_async_mailer_supports_resources_and_async_callbacks() -> None:
    async def scenario() -> None:
        client = FakeAsyncRequester(
            actions=[
                make_json_response(200, {"id": "email_123"}),
                make_json_response(200, {"ok": True, "data": {"status": "ok"}}),
            ]
        )
        mailer = AsyncMailer(
            base_url="https://mailer.example.com/base",
            client=client,
            auth=BearerAuthStrategy(
                token=lambda context: _async_token(context.path),
                header_name="x-auth-token",
                prefix="Token",
            ),
        )

        try:
            send_result = await mailer.emails.send(
                {
                    "from": "a@example.com",
                    "to": "b@example.com",
                    "subject": "Hello",
                    "text": "World",
                }
            )
            raw_result = await mailer.request(
                "GET",
                "/healthz",
                RequestOptions(
                    authenticated=False,
                    middleware=[_async_middleware],
                    parse_response=_async_parse_response,
                    transform_response=_async_transform_response,
                ),
            )
        finally:
            await mailer.aclose()

        assert send_result == {"id": "email_123"}
        assert client.calls[0]["headers"].get("x-auth-token") == "Token token-for:/emails"
        assert client.calls[0]["url"] == "https://mailer.example.com/base/emails"
        assert raw_result == {"status": "ok", "via": "async"}
        assert client.calls[1]["headers"].get("x-async") == "true"
        assert client.closed is False

    asyncio.run(scenario())


def test_async_mailer_retries_with_async_predicates() -> None:
    async def scenario() -> None:
        client = FakeAsyncRequester(
            actions=[
                make_json_response(
                    500,
                    {"ok": False, "error": {"code": "TEMP", "message": "retry"}},
                ),
                make_json_response(200, {"ok": True, "data": {"recovered": True}}),
            ]
        )
        mailer = AsyncMailer(
            "mk_live_123_secret",
            base_url="https://mailer.example.com",
            client=client,
        )

        result = await mailer.request(
            "GET",
            "/retry",
            RequestOptions(
                retry=RetryOptions(
                    max_attempts=2,
                    delay_seconds=lambda _context: _async_zero(),
                    should_retry=lambda context: _async_should_retry(context),
                )
            ),
        )

        assert result == {"recovered": True}
        assert len(client.calls) == 2

    asyncio.run(scenario())


def test_async_sendstack_resources_support_default_x_api_key_auth() -> None:
    async def scenario() -> None:
        client = FakeAsyncRequester(
            actions=[
                make_json_response(
                    200,
                    {
                        "channel": "email",
                        "estimated_units": 1,
                        "available_units": 99,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "email_v1"},
                    },
                ),
                make_json_response(
                    202,
                    {
                        "id": "message_async_1",
                        "status": "queued",
                        "channel": "email",
                    },
                ),
                make_json_response(
                    200,
                    {
                        "channel": "sms",
                        "estimated_units": 2,
                        "available_units": 98,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "sms_v1"},
                    },
                ),
                make_json_response(
                    202,
                    {
                        "id": "sms_async_1",
                        "status": "queued",
                        "channel": "sms",
                    },
                ),
                make_json_response(
                    200,
                    {
                        "items": [{"id": "sms_async_1", "channel": "sms"}],
                        "next_cursor": None,
                        "has_more": False,
                        "limit": 5,
                    },
                ),
                make_json_response(
                    200,
                    {
                        "id": "sms_async_1",
                        "status": "queued",
                        "channel": "sms",
                    },
                ),
                make_json_response(
                    200,
                    {
                        "channel": "whatsapp",
                        "estimated_units": 1,
                        "available_units": 98,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "whatsapp_v1"},
                    },
                ),
                make_json_response(
                    202,
                    {
                        "id": "wa_async_1",
                        "status": "queued",
                        "channel": "whatsapp",
                    },
                ),
                make_json_response(
                    200,
                    {
                        "items": [{"id": "wa_async_1", "channel": "whatsapp"}],
                        "next_cursor": None,
                        "has_more": False,
                        "limit": 5,
                    },
                ),
                make_json_response(
                    200,
                    {
                        "id": "wa_async_1",
                        "status": "queued",
                        "channel": "whatsapp",
                    },
                ),
                make_json_response(200, {"status": "alive", "uptime_s": 1.0}),
            ]
        )
        mailer = AsyncMailer(
            "sk_async_test",
            base_url="https://sendstack.example.com/api/v1",
            client=client,
        )

        try:
            quote = await mailer.emails.quote(
                {
                    "from": "sender@example.com",
                    "to": "recipient@example.com",
                    "subject": "Quoted email",
                    "text": "Quoted email",
                }
            )
            send = await mailer.emails.send(
                {
                    "from": "sender@example.com",
                    "to": "recipient@example.com",
                    "subject": "Queued email",
                    "text": "Queued email",
                }
            )
            sms_quote = await mailer.sms.quote(
                {
                    "from": "SENDSTACK",
                    "to": "+254722111222",
                    "text": "Quoted SMS",
                }
            )
            sms_send = await mailer.sms.send(
                {
                    "from": "SENDSTACK",
                    "to": "+254722111222",
                    "text": "Queued SMS",
                }
            )
            sms_list = await mailer.sms.list(limit=5, status="queued")
            sms_get = await mailer.sms.get("sms_async_1")
            whatsapp_quote = await mailer.whatsapp.quote(
                {
                    "from": "WABA",
                    "to": "+254733000333",
                    "text": "Quoted WhatsApp",
                    "template_variables": {"first_name": "Mercy"},
                }
            )
            whatsapp_send = await mailer.whatsapp.send(
                {
                    "from": "WABA",
                    "to": "+254733000333",
                    "text": "Queued WhatsApp",
                    "template_variables": {"first_name": "Mercy"},
                }
            )
            whatsapp_list = await mailer.whatsapp.list(limit=5, status="queued")
            whatsapp_get = await mailer.whatsapp.get("wa_async_1")
            live = await mailer.health.live()
        finally:
            await mailer.aclose()

        assert quote["estimated_units"] == 1
        assert send["id"] == "message_async_1"
        assert sms_quote["channel"] == "sms"
        assert sms_send["id"] == "sms_async_1"
        assert sms_list["items"][0]["id"] == "sms_async_1"
        assert sms_get["channel"] == "sms"
        assert whatsapp_quote["channel"] == "whatsapp"
        assert whatsapp_send["id"] == "wa_async_1"
        assert whatsapp_list["items"][0]["id"] == "wa_async_1"
        assert whatsapp_get["channel"] == "whatsapp"
        assert live["status"] == "alive"
        assert client.calls[0]["headers"].get("x-api-key") == "sk_async_test"
        assert client.calls[0]["url"] == "https://sendstack.example.com/api/v1/emails/quote"
        assert client.calls[1]["url"] == "https://sendstack.example.com/api/v1/emails"
        assert client.calls[2]["url"] == "https://sendstack.example.com/api/v1/sms/quote"
        assert client.calls[4]["url"] == "https://sendstack.example.com/api/v1/sms?limit=5&status=queued"
        assert client.calls[6]["url"] == "https://sendstack.example.com/api/v1/whatsapp/messages/quote"
        assert json.loads(client.calls[6]["content"]) == {
            "from": "WABA",
            "to": "+254733000333",
            "text": "Quoted WhatsApp",
            "variables": {"first_name": "Mercy"},
        }
        assert client.calls[10]["url"] == "https://sendstack.example.com/livez"
        assert client.calls[10]["headers"].get("x-api-key") is None

    asyncio.run(scenario())


def test_async_sendstack_merchant_resources_support_control_plane_routes() -> None:
    async def scenario() -> None:
        client = FakeAsyncRequester(
            actions=[
                make_json_response(
                    200,
                    {
                        "items": [{"id": "message_async_merchant_1", "channel": "email"}],
                        "next_cursor": None,
                        "has_more": False,
                        "limit": 12,
                    },
                ),
                make_json_response(
                    200,
                    {"id": "message_async_merchant_1", "channel": "email"},
                ),
                make_json_response(
                    200,
                    {
                        "channel": "email",
                        "estimated_units": 1,
                        "available_units": 60,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "email_v1"},
                    },
                ),
                make_json_response(
                    200,
                    {
                        "channel": "email",
                        "estimated_units": 2,
                        "available_units": 60,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "email_v1", "delivery_mode": "group"},
                    },
                ),
                make_json_response(
                    202,
                    {"id": "merchant_async_email_1", "channel": "email", "status": "queued"},
                ),
                make_json_response(
                    202,
                    {
                        "messages": [{"id": "merchant_async_email_2"}],
                        "recipient_count": 1,
                        "delivery_mode": "group",
                    },
                ),
                make_json_response(
                    200,
                    {
                        "channel": "sms",
                        "estimated_units": 1,
                        "available_units": 60,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "sms_v1"},
                    },
                ),
                make_json_response(
                    202,
                    {"id": "merchant_async_sms_1", "channel": "sms", "status": "queued"},
                ),
                make_json_response(
                    200,
                    {
                        "channel": "whatsapp",
                        "estimated_units": 1,
                        "available_units": 60,
                        "reserved_units": 0,
                        "can_send": True,
                        "pricing": {"pricing_model": "whatsapp_v1"},
                    },
                ),
                make_json_response(
                    202,
                    {"id": "merchant_async_wa_1", "channel": "whatsapp", "status": "queued"},
                ),
            ]
        )
        mailer = AsyncMailer(
            base_url="https://sendstack.example.com/api/v1",
            client=client,
            auth=BearerAuthStrategy(token=lambda _context: "merchant-async-token"),
        )

        try:
            listing = await mailer.merchant.messages.list(
                "merchant_async_123",
                limit=12,
                channel="whatsapp",
                status="queued",
            )
            message = await mailer.merchant.messages.get(
                "merchant_async_123",
                "message_async_merchant_1",
            )
            quote = await mailer.merchant.emails.quote(
                "merchant_async_123",
                {
                    "from": "sender@example.com",
                    "to": "recipient@example.com",
                    "subject": "Merchant async email",
                    "text": "Merchant async email",
                },
            )
            group_quote = await mailer.merchant.emails.quote_group(
                "merchant_async_123",
                {
                    "from": "sender@example.com",
                    "to": ["one@example.com", "two@example.com"],
                    "subject": "Async group quote",
                    "text": "Async group quote",
                },
            )
            send = await mailer.merchant.emails.send(
                "merchant_async_123",
                {
                    "from": "sender@example.com",
                    "to": "recipient@example.com",
                    "subject": "Merchant async email",
                    "text": "Queued merchant async email",
                },
            )
            group_send = await mailer.merchant.emails.send_group(
                "merchant_async_123",
                {
                    "from": "sender@example.com",
                    "to": ["one@example.com"],
                    "subject": "Async group send",
                    "text": "Queued async group email",
                },
            )
            sms_quote = await mailer.merchant.sms.quote(
                "merchant_async_123",
                {
                    "from": "SENDSTACK",
                    "to": "+254722111222",
                    "text": "Async merchant SMS",
                },
            )
            sms_send = await mailer.merchant.sms.send(
                "merchant_async_123",
                {
                    "from": "SENDSTACK",
                    "to": "+254722111222",
                    "text": "Queued async merchant SMS",
                },
            )
            whatsapp_quote = await mailer.merchant.whatsapp.quote(
                "merchant_async_123",
                {
                    "from": "WABA",
                    "to": "+254733000333",
                    "text": "Async merchant WhatsApp",
                    "template_variables": {"first_name": "Mercy"},
                },
            )
            whatsapp_send = await mailer.merchant.whatsapp.send(
                "merchant_async_123",
                {
                    "from": "WABA",
                    "to": "+254733000333",
                    "text": "Queued async merchant WhatsApp",
                    "template_variables": {"first_name": "Mercy"},
                },
            )
        finally:
            await mailer.aclose()

        assert listing["items"][0]["id"] == "message_async_merchant_1"
        assert message["id"] == "message_async_merchant_1"
        assert quote["channel"] == "email"
        assert group_quote["pricing"]["delivery_mode"] == "group"
        assert send["id"] == "merchant_async_email_1"
        assert group_send["delivery_mode"] == "group"
        assert sms_quote["channel"] == "sms"
        assert sms_send["id"] == "merchant_async_sms_1"
        assert whatsapp_quote["channel"] == "whatsapp"
        assert whatsapp_send["id"] == "merchant_async_wa_1"
        assert (
            client.calls[0]["url"]
            == "https://sendstack.example.com/api/v1/merchants/merchant_async_123/messages?limit=12&channel=whatsapp&status=queued"
        )
        assert client.calls[0]["headers"].get("authorization") == "Bearer merchant-async-token"
        assert client.calls[5]["url"] == (
            "https://sendstack.example.com/api/v1/merchants/merchant_async_123/messages/email/group"
        )
        assert json.loads(client.calls[8]["content"]) == {
            "from": "WABA",
            "to": "+254733000333",
            "text": "Async merchant WhatsApp",
            "variables": {"first_name": "Mercy"},
        }

    asyncio.run(scenario())


def test_mailer_can_omit_api_key_and_defaults_to_no_auth() -> None:
    mailer = Mailer(
        base_url="https://sendstack.example.com/api/v1",
        client=FakeSyncRequester(actions=[]),
    )

    assert mailer.api_key == ""


def test_async_mailer_can_omit_api_key_and_defaults_to_no_auth() -> None:
    async def scenario() -> None:
        mailer = AsyncMailer(
            base_url="https://sendstack.example.com/api/v1",
            client=FakeAsyncRequester(actions=[]),
        )
        assert mailer.api_key == ""
        await mailer.aclose()

    asyncio.run(scenario())


async def _async_token(path: str) -> str:
    return f"token-for:{path}"


async def _async_middleware(context: Any, next_call: Any) -> Any:
    context.headers["x-async"] = "true"
    return await next_call(context)


async def _async_parse_response(response: httpx.Response, _context: Any) -> object:
    return {"status": response.json()["data"]["status"]}


async def _async_transform_response(context: Any) -> object:
    payload = dict(context.payload)
    payload["via"] = "async"
    return payload


async def _async_zero() -> int:
    return 0


async def _async_should_retry(context: Any) -> bool:
    return context.response is not None and context.response.status_code == 500
