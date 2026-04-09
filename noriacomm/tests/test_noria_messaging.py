from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
import pytest

from noriacomm import (
    META_GRAPH_API_VERSION,
    AsyncMessagingClient,
    ConfigurationError,
    GatewayError,
    MessagingClient,
    MetaWhatsAppGateway,
    OnfonSmsGateway,
    RequestOptions,
    RetryPolicy,
    SmsGroupUpsertRequest,
    SmsMessage,
    SmsSendRequest,
    SmsTemplateUpsertRequest,
    WhatsAppCatalogMessageRequest,
    WhatsAppContact,
    WhatsAppContactAddress,
    WhatsAppContactName,
    WhatsAppContactPhone,
    WhatsAppContactsRequest,
    WhatsAppFlowMessageRequest,
    WhatsAppInteractiveHeader,
    WhatsAppInteractiveRequest,
    WhatsAppInteractiveRow,
    WhatsAppInteractiveSection,
    WhatsAppLocationRequest,
    WhatsAppMediaInfo,
    WhatsAppMediaRequest,
    WhatsAppMediaUploadRequest,
    WhatsAppProductItem,
    WhatsAppProductListRequest,
    WhatsAppProductMessageRequest,
    WhatsAppProductSection,
    WhatsAppReactionRequest,
    WhatsAppTemplateButtonDefinition,
    WhatsAppTemplateComponent,
    WhatsAppTemplateComponentDefinition,
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDeleteRequest,
    WhatsAppTemplateListRequest,
    WhatsAppTemplateParameter,
    WhatsAppTemplateRequest,
    WhatsAppTemplateUpdateRequest,
    WhatsAppTextRequest,
    fastapi_parse_meta_delivery_events,
    fastapi_parse_meta_inbound_messages,
    flask_parse_meta_inbound_messages,
    flask_parse_onfon_delivery_report,
    resolve_meta_subscription_challenge,
    verify_meta_signature,
)


@dataclass(slots=True)
class FakeSyncHttpClient:
    responses: list[httpx.Response]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake responses left.")
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class FakeAsyncHttpClient:
    responses: list[httpx.Response]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake responses left.")
        return self.responses.pop(0)

    async def aclose(self) -> None:
        self.closed = True


@dataclass(slots=True)
class FakeFastAPIRequest:
    query_params: dict[str, object] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    payload: bytes = b"{}"

    async def body(self) -> bytes:
        return self.payload


@dataclass(slots=True)
class FakeFlaskRequest:
    args: dict[str, object] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    payload: bytes = b"{}"
    json_payload: object = None

    def get_data(self) -> bytes:
        return self.payload

    def get_json(self, silent: bool = True) -> object:
        return self.json_payload


def make_response(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        headers={"content-type": "application/json"},
    )


def test_sms_client_sends_onfon_messages_and_formats_payload() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [
                        {
                            "MobileNumber": "254712345678",
                            "MessageId": "msg-123",
                        }
                    ],
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=client,
    )
    messaging = MessagingClient(sms=gateway)

    result = messaging.sms.send(
        SmsSendRequest(
            messages=[SmsMessage(recipient="254712345678", text="Hello Alice", reference="user-1")],
            is_unicode=False,
            is_flash=False,
            schedule_at=datetime(2026, 4, 8, 9, 30),
        )
    )

    assert result.accepted is True
    assert result.submitted_count == 1
    assert result.messages[0].provider_message_id == "msg-123"
    assert messaging.sms.gateway is not None
    assert messaging.sms.gateway.client.calls[0]["method"] == "POST"
    assert messaging.sms.gateway.client.calls[0]["url"] == "https://api.onfonmedia.co.ke/v1/sms/SendBulkSMS"
    assert messaging.sms.gateway.client.calls[0]["headers"]["AccessKey"] == "access-key"
    assert messaging.sms.gateway.client.calls[0]["json"]["SenderId"] == "NORIA"
    assert messaging.sms.gateway.client.calls[0]["json"]["ApiKey"] == "api-key"
    assert messaging.sms.gateway.client.calls[0]["json"]["ClientId"] == "client-id"
    assert messaging.sms.gateway.client.calls[0]["json"]["IsUnicode"] is False
    assert messaging.sms.gateway.client.calls[0]["json"]["IsFlash"] is False
    assert messaging.sms.gateway.client.calls[0]["json"]["ScheduleDateTime"] == "2026-04-08 09:30"


def test_onfon_gateway_marks_missing_message_ids_as_failed() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": "000",
                    "ErrorDescription": "Success",
                    "Data": [{"MobileNumber": "254712345678"}],
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=client,
    )

    result = gateway.send(
        SmsSendRequest(messages=[SmsMessage(recipient="254712345678", text="Hello Alice")])
    )

    assert result.accepted is True
    assert result.failed_count == 1
    assert result.messages[0].status == "failed"
    assert result.messages[0].provider_error_code == "MISSING_MESSAGE_ID"


def test_onfon_gateway_raises_gateway_error_on_top_level_provider_failure() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": "007",
                    "ErrorDescription": "Invalid API credentials",
                    "Data": [],
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=client,
    )

    with pytest.raises(GatewayError) as exc:
        gateway.send(
            SmsSendRequest(messages=[SmsMessage(recipient="254712345678", text="Hello Alice")])
        )

    assert exc.value.provider == "onfon"
    assert exc.value.error_code == "007"
    assert exc.value.error_description == "Invalid API credentials"


def test_onfon_gateway_parses_balance_response() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [{"PluginType": "SMS", "Credits": "KSh7578560.8000"}],
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        client=client,
    )

    balance = gateway.get_balance()

    assert len(balance.entries) == 1
    assert balance.entries[0].label == "SMS"
    assert balance.entries[0].credits_raw == "KSh7578560.8000"
    assert str(balance.entries[0].credits) == "7578560.8000"
    assert client.calls[0]["method"] == "GET"
    assert client.calls[0]["params"] == {"ApiKey": "api-key", "ClientId": "client-id"}


def test_onfon_gateway_parses_delivery_reports() -> None:
    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
    )

    report = gateway.parse_delivery_report(
        {
            "messageId": ["msg-123"],
            "mobile": "254712345678",
            "status": "DELIVRD",
            "errorCode": "000",
            "submitDate": "2026-04-08 09:30",
            "doneDate": "2026-04-08 09:31",
            "shortMessage": "Hello Alice",
        }
    )

    assert report is not None
    assert report.channel == "sms"
    assert report.provider == "onfon"
    assert report.provider_message_id == "msg-123"
    assert report.recipient == "254712345678"
    assert report.state == "delivered"
    assert report.provider_status == "DELIVRD"


def test_onfon_gateway_lists_groups() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [
                        {
                            "GroupId": 33,
                            "GroupName": "Customers",
                            "ContactCount": 21,
                        }
                    ],
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        client=client,
    )

    groups = gateway.list_groups()

    assert len(groups) == 1
    assert groups[0].group_id == "33"
    assert groups[0].name == "Customers"
    assert groups[0].contact_count == 21
    assert client.calls[0]["method"] == "GET"
    assert client.calls[0]["url"] == "https://api.onfonmedia.co.ke/v1/sms/Group"


def test_onfon_gateway_creates_templates() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": "Template Added successfully.",
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        client=client,
    )

    result = gateway.create_template(
        SmsTemplateUpsertRequest(
            name="promo_offer",
            body="Hello ##Name##, use code SAVE10 today.",
        )
    )

    assert result.success is True
    assert result.message == "Template Added successfully."
    assert client.calls[0]["method"] == "POST"
    assert client.calls[0]["json"]["TemplateName"] == "promo_offer"
    assert client.calls[0]["json"]["MessageTemplate"] == "Hello ##Name##, use code SAVE10 today."


def test_sms_service_exposes_onfon_group_management() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": "success#New Group added successfully.",
                },
            )
        ]
    )

    messaging = MessagingClient(
        sms=OnfonSmsGateway(
            access_key="access-key",
            api_key="api-key",
            client_id="client-id",
            client=client,
        )
    )

    result = messaging.sms.create_group(SmsGroupUpsertRequest(name="Customers"))

    assert result.success is True
    assert result.message == "success#New Group added successfully."
    assert client.calls[0]["json"]["GroupName"] == "Customers"


def test_onfon_gateway_requires_sender_id_for_send() -> None:
    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
    )

    with pytest.raises(ConfigurationError):
        gateway.send(SmsSendRequest(messages=[SmsMessage(recipient="254712345678", text="Hello")]))


def test_onfon_gateway_uses_client_retry_policy_when_retry_true_is_requested() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(500, {"detail": "temporary failure"}),
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [{"MobileNumber": "254712345678", "MessageId": "msg-123"}],
                },
            ),
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=client,
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("POST",),
            retry_on_statuses=(500,),
            base_delay_seconds=0.0,
        ),
    )

    result = gateway.send(
        SmsSendRequest(messages=[SmsMessage(recipient="254712345678", text="Hello Alice")]),
        options=RequestOptions(retry=True),
    )

    assert result.submitted_count == 1
    assert len(client.calls) == 2


def test_async_messaging_client_sends_messages_with_httpx_async_client() -> None:
    async_client = FakeAsyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [
                        {
                            "MobileNumber": "254712345678",
                            "MessageId": "msg-async-123",
                        }
                    ],
                },
            )
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        async_client=async_client,
    )

    async def run() -> None:
        async with AsyncMessagingClient(sms=gateway) as messaging:
            result = await messaging.sms.send(
                SmsSendRequest(messages=[SmsMessage(recipient="254712345678", text="Hello Alice")])
            )

            assert result.submitted_count == 1
            assert result.messages[0].provider_message_id == "msg-async-123"
            assert async_client.calls[0]["method"] == "POST"
            assert async_client.calls[0]["headers"]["AccessKey"] == "access-key"

        assert async_client.closed is False

    asyncio.run(run())


def test_meta_whatsapp_gateway_sends_text_messages() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "messaging_product": "whatsapp",
                    "contacts": [{"input": "254712345678", "wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.123", "message_status": "accepted"}],
                },
            )
        ]
    )

    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        client=client,
    )

    result = gateway.send_text(
        WhatsAppTextRequest(
            recipient="254712345678",
            text="Hello from WhatsApp",
            preview_url=False,
            reply_to_message_id="wamid.original",
        )
    )

    assert result.accepted is True
    assert result.messages[0].provider_message_id == "wamid.123"
    assert client.calls[0]["url"] == f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/123456789/messages"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer meta-token"
    assert client.calls[0]["json"]["messaging_product"] == "whatsapp"
    assert client.calls[0]["json"]["text"]["body"] == "Hello from WhatsApp"
    assert client.calls[0]["json"]["context"] == {"message_id": "wamid.original"}


def test_meta_whatsapp_gateway_sends_templates() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "messaging_product": "whatsapp",
                    "contacts": [{"input": "254712345678", "wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.456", "message_status": "accepted"}],
                },
            )
        ]
    )

    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        client=client,
    )

    result = gateway.send_template(
        WhatsAppTemplateRequest(
            recipient="254712345678",
            template_name="shipment_update",
            language_code="en_US",
            components=[
                WhatsAppTemplateComponent(
                    type="body",
                    parameters=[
                        WhatsAppTemplateParameter(type="text", value="Alice"),
                        WhatsAppTemplateParameter(type="text", value="Order-123"),
                    ],
                )
            ],
        )
    )

    assert result.messages[0].provider_message_id == "wamid.456"
    template = client.calls[0]["json"]["template"]
    assert template["name"] == "shipment_update"
    assert template["language"] == {"code": "en_US"}
    assert template["components"][0]["parameters"][0]["text"] == "Alice"


def test_meta_whatsapp_gateway_manages_templates() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "data": [
                        {
                            "id": "tmpl-1",
                            "name": "seasonal_promotion",
                            "language": "en",
                            "category": "MARKETING",
                            "status": "APPROVED",
                            "components": [
                                {
                                    "type": "BODY",
                                    "text": "Hello {{1}}",
                                    "example": {"body_text": [["Alice"]]},
                                }
                            ],
                        }
                    ],
                    "paging": {"cursors": {"before": "prev-1", "after": "next-1"}},
                    "summary": {"total_count": 1, "message_template_limit": 6000},
                },
            ),
            make_response(
                200,
                {
                    "id": "tmpl-1",
                    "name": "seasonal_promotion",
                    "language": "en",
                    "category": "MARKETING",
                    "status": "APPROVED",
                    "parameter_format": "POSITIONAL",
                    "message_send_ttl_seconds": 600,
                    "components": [
                        {
                            "type": "BODY",
                            "text": "Hello {{1}}",
                            "example": {"body_text": [["Alice"]]},
                        }
                    ],
                },
            ),
            make_response(
                200,
                {
                    "id": "tmpl-2",
                    "status": "PENDING",
                    "category": "MARKETING",
                },
            ),
            make_response(
                200,
                {
                    "success": True,
                    "id": "tmpl-1",
                    "name": "seasonal_promotion",
                    "category": "UTILITY",
                },
            ),
            make_response(200, {"success": True}),
        ]
    )

    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        whatsapp_business_account_id="9988776655",
        client=client,
    )

    listed = gateway.list_templates(
        WhatsAppTemplateListRequest(
            category=("marketing",),
            status=("approved", "paused"),
            fields=("name", "category"),
            summary_fields=("total_count", "message_template_limit"),
            limit=25,
            after="next-1",
        )
    )
    template = gateway.get_template("tmpl-1", fields=("name", "status"))
    created = gateway.create_template(
        WhatsAppTemplateCreateRequest(
            name="seasonal_promotion",
            language="en",
            category="marketing",
            components=(
                WhatsAppTemplateComponentDefinition(
                    type="body",
                    text="Hello {{1}}",
                    example={"body_text": [["Alice"]]},
                ),
                WhatsAppTemplateComponentDefinition(
                    type="buttons",
                    buttons=(
                        WhatsAppTemplateButtonDefinition(
                            type="quick_reply",
                            text="Unsubscribe",
                        ),
                    ),
                ),
            ),
            allow_category_change=True,
            parameter_format="positional",
            message_send_ttl_seconds=600,
        )
    )
    updated = gateway.update_template(
        "tmpl-1",
        WhatsAppTemplateUpdateRequest(
            category="utility",
            components=(
                WhatsAppTemplateComponentDefinition(type="body", text="Updated {{1}}"),
            ),
        ),
    )
    deleted = gateway.delete_template(
        WhatsAppTemplateDeleteRequest(name="seasonal_promotion", template_id="tmpl-1")
    )

    assert listed.templates[0].template_id == "tmpl-1"
    assert listed.summary is not None
    assert listed.summary.total_count == 1
    assert listed.after == "next-1"
    assert template.parameter_format == "POSITIONAL"
    assert template.message_send_ttl_seconds == 600
    assert created.template_id == "tmpl-2"
    assert created.status == "PENDING"
    assert updated.success is True
    assert updated.category == "UTILITY"
    assert deleted.deleted is True

    assert client.calls[0]["url"] == (
        f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/9988776655/message_templates"
    )
    assert client.calls[0]["params"] == {
        "category": "MARKETING",
        "status": "APPROVED,PAUSED",
        "fields": "name,category",
        "summary": "total_count,message_template_limit",
        "limit": "25",
        "after": "next-1",
    }
    assert client.calls[1]["url"] == f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/tmpl-1"
    assert client.calls[1]["params"] == {"fields": "name,status"}
    assert client.calls[2]["json"]["category"] == "MARKETING"
    assert client.calls[2]["json"]["allow_category_change"] is True
    assert client.calls[2]["json"]["parameter_format"] == "POSITIONAL"
    assert client.calls[2]["json"]["components"][1]["buttons"][0]["type"] == "QUICK_REPLY"
    assert client.calls[3]["json"]["category"] == "UTILITY"
    assert client.calls[3]["json"]["components"][0]["type"] == "BODY"
    assert client.calls[4]["params"] == {"name": "seasonal_promotion", "hsm_id": "tmpl-1"}


def test_meta_whatsapp_gateway_manages_templates_async() -> None:
    async def run() -> None:
        client = FakeAsyncHttpClient(
            responses=[
                make_response(
                    200,
                    {
                        "data": [
                            {
                                "id": "tmpl-async-1",
                                "name": "shipment_async",
                                "language": "en_US",
                                "category": "UTILITY",
                                "status": "APPROVED",
                            }
                        ]
                    },
                ),
                make_response(
                    200,
                    {
                        "id": "tmpl-async-1",
                        "name": "shipment_async",
                        "status": "APPROVED",
                    },
                ),
                make_response(
                    200,
                    {
                        "id": "tmpl-async-2",
                        "status": "PENDING",
                    },
                ),
                make_response(
                    200,
                    {
                        "success": True,
                        "id": "tmpl-async-1",
                        "category": "UTILITY",
                    },
                ),
                make_response(200, {"success": True}),
            ]
        )

        gateway = MetaWhatsAppGateway(
            access_token="meta-token",
            phone_number_id="123456789",
            whatsapp_business_account_id="9988776655",
            async_client=client,
        )

        listed = await gateway.alist_templates()
        template = await gateway.aget_template("tmpl-async-1", fields=("name",))
        created = await gateway.acreate_template(
            WhatsAppTemplateCreateRequest(
                name="shipment_async",
                language="en_US",
                category="utility",
                components=(
                    WhatsAppTemplateComponentDefinition(type="body", text="Hello {{1}}"),
                ),
            )
        )
        updated = await gateway.aupdate_template(
            "tmpl-async-1",
            WhatsAppTemplateUpdateRequest(
                category="utility",
                components=(
                    WhatsAppTemplateComponentDefinition(type="body", text="Updated {{1}}"),
                ),
            ),
        )
        deleted = await gateway.adelete_template(
            WhatsAppTemplateDeleteRequest(template_ids=("tmpl-async-1",))
        )

        assert listed.templates[0].template_id == "tmpl-async-1"
        assert template.template_id == "tmpl-async-1"
        assert created.template_id == "tmpl-async-2"
        assert updated.success is True
        assert deleted.deleted is True
        assert client.calls[4]["params"] == {"hsm_ids": '["tmpl-async-1"]'}

    asyncio.run(run())


def test_meta_whatsapp_gateway_sends_media_location_contacts_reaction_and_interactive() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.media", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.location", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.contacts", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.reaction", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.interactive", "message_status": "accepted"}],
                },
            ),
        ]
    )

    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        client=client,
    )

    media = gateway.send_media(
        WhatsAppMediaRequest(
            recipient="254712345678",
            media_type="image",
            link="https://cdn.example.com/poster.png",
            caption="Promo poster",
            reply_to_message_id="wamid.original",
        )
    )
    location = gateway.send_location(
        WhatsAppLocationRequest(
            recipient="254712345678",
            latitude=-1.2921,
            longitude=36.8219,
            name="Noria HQ",
            address="Westlands, Nairobi",
        )
    )
    contacts = gateway.send_contacts(
        WhatsAppContactsRequest(
            recipient="254712345678",
            contacts=[
                WhatsAppContact(
                    name=WhatsAppContactName(
                        formatted_name="Alice Doe",
                        first_name="Alice",
                        last_name="Doe",
                    ),
                    phones=[
                        WhatsAppContactPhone(
                            phone="+254712345678",
                            type="CELL",
                            wa_id="254712345678",
                        )
                    ],
                    addresses=[
                        WhatsAppContactAddress(
                            city="Nairobi",
                            country="Kenya",
                            type="HOME",
                        )
                    ],
                )
            ],
        )
    )
    reaction = gateway.send_reaction(
        WhatsAppReactionRequest(
            recipient="254712345678",
            message_id="wamid.original",
            emoji="👍",
        )
    )
    interactive = gateway.send_interactive(
        WhatsAppInteractiveRequest(
            recipient="254712345678",
            interactive_type="list",
            body_text="Choose a product",
            header=WhatsAppInteractiveHeader(type="text", text="Catalog"),
            footer_text="Powered by Noria",
            button_text="View options",
            sections=[
                WhatsAppInteractiveSection(
                    title="Plans",
                    rows=[
                        WhatsAppInteractiveRow(
                            identifier="starter",
                            title="Starter",
                            description="Best for small teams",
                        )
                    ],
                )
            ],
        )
    )

    assert media.messages[0].provider_message_id == "wamid.media"
    assert location.messages[0].provider_message_id == "wamid.location"
    assert contacts.messages[0].provider_message_id == "wamid.contacts"
    assert reaction.messages[0].provider_message_id == "wamid.reaction"
    assert interactive.messages[0].provider_message_id == "wamid.interactive"

    assert client.calls[0]["json"]["image"]["link"] == "https://cdn.example.com/poster.png"
    assert client.calls[0]["json"]["image"]["caption"] == "Promo poster"
    assert client.calls[0]["json"]["context"] == {"message_id": "wamid.original"}
    assert client.calls[1]["json"]["location"]["latitude"] == -1.2921
    assert client.calls[1]["json"]["location"]["name"] == "Noria HQ"
    assert client.calls[2]["json"]["contacts"][0]["name"]["formatted_name"] == "Alice Doe"
    assert client.calls[2]["json"]["contacts"][0]["phones"][0]["wa_id"] == "254712345678"
    assert client.calls[3]["json"]["reaction"] == {
        "message_id": "wamid.original",
        "emoji": "👍",
    }
    assert client.calls[4]["json"]["interactive"]["type"] == "list"
    assert client.calls[4]["json"]["interactive"]["action"]["button"] == "View options"
    assert (
        client.calls[4]["json"]["interactive"]["action"]["sections"][0]["rows"][0]["id"]
        == "starter"
    )


def test_async_messaging_client_sends_whatsapp_media_messages() -> None:
    async_client = FakeAsyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.async.media", "message_status": "accepted"}],
                },
            )
        ]
    )
    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        async_client=async_client,
    )

    async def run() -> None:
        async with AsyncMessagingClient(whatsapp=gateway) as messaging:
            result = await messaging.whatsapp.send_media(
                WhatsAppMediaRequest(
                    recipient="254712345678",
                    media_type="document",
                    media_id="media-123",
                    filename="brochure.pdf",
                )
            )

            assert result.messages[0].provider_message_id == "wamid.async.media"
            assert async_client.calls[0]["json"]["document"] == {
                "id": "media-123",
                "filename": "brochure.pdf",
            }

        assert async_client.closed is False

    asyncio.run(run())


def test_meta_whatsapp_gateway_supports_commerce_flow_and_media_helpers() -> None:
    client = FakeSyncHttpClient(
        responses=[
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.catalog", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.product", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.product-list", "message_status": "accepted"}],
                },
            ),
            make_response(
                200,
                {
                    "contacts": [{"wa_id": "254712345678"}],
                    "messages": [{"id": "wamid.flow", "message_status": "accepted"}],
                },
            ),
            make_response(200, {"id": "media-upload-1"}),
            make_response(
                200,
                {
                    "id": "media-upload-1",
                    "url": "https://lookaside.fbsbx.com/media/1",
                    "mime_type": "image/png",
                    "sha256": "abc123",
                    "file_size": "2048",
                },
            ),
            make_response(200, {"success": True}),
        ]
    )
    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        client=client,
    )

    catalog = gateway.send_catalog(
        WhatsAppCatalogMessageRequest(
            recipient="254712345678",
            body_text="Browse the latest collection",
            thumbnail_product_retailer_id="sku-1",
        )
    )
    product = gateway.send_product(
        WhatsAppProductMessageRequest(
            recipient="254712345678",
            catalog_id="catalog-1",
            product_retailer_id="sku-1",
            body_text="Featured product",
        )
    )
    product_list = gateway.send_product_list(
        WhatsAppProductListRequest(
            recipient="254712345678",
            catalog_id="catalog-1",
            header=WhatsAppInteractiveHeader(type="text", text="Store"),
            body_text="Choose a bundle",
            sections=(
                WhatsAppProductSection(
                    title="Popular",
                    product_items=(
                        WhatsAppProductItem(product_retailer_id="sku-1"),
                        WhatsAppProductItem(product_retailer_id="sku-2"),
                    ),
                ),
            ),
        )
    )
    flow = gateway.send_flow(
        WhatsAppFlowMessageRequest(
            recipient="254712345678",
            body_text="Complete onboarding",
            flow_id="flow-123",
            flow_cta="Open flow",
            flow_token="flow-token",
            flow_action_payload={"screen": "DETAILS", "data": {"customer_id": "cust-1"}},
        )
    )
    upload = gateway.upload_media(
        WhatsAppMediaUploadRequest(
            filename="poster.png",
            content=b"image-bytes",
            mime_type="image/png",
        )
    )
    media = gateway.get_media("media-upload-1")
    deleted = gateway.delete_media("media-upload-1")

    assert catalog.messages[0].provider_message_id == "wamid.catalog"
    assert product.messages[0].provider_message_id == "wamid.product"
    assert product_list.messages[0].provider_message_id == "wamid.product-list"
    assert flow.messages[0].provider_message_id == "wamid.flow"
    assert upload.media_id == "media-upload-1"
    assert media == WhatsAppMediaInfo(
        provider="meta",
        media_id="media-upload-1",
        url="https://lookaside.fbsbx.com/media/1",
        mime_type="image/png",
        sha256="abc123",
        file_size=2048,
        raw={
            "id": "media-upload-1",
            "url": "https://lookaside.fbsbx.com/media/1",
            "mime_type": "image/png",
            "sha256": "abc123",
            "file_size": "2048",
        },
    )
    assert deleted.deleted is True

    assert client.calls[0]["json"]["interactive"]["action"] == {
        "name": "catalog_message",
        "parameters": {"thumbnail_product_retailer_id": "sku-1"},
    }
    assert client.calls[1]["json"]["interactive"]["action"] == {
        "catalog_id": "catalog-1",
        "product_retailer_id": "sku-1",
    }
    assert client.calls[2]["json"]["interactive"]["action"]["sections"][0]["product_items"] == [
        {"product_retailer_id": "sku-1"},
        {"product_retailer_id": "sku-2"},
    ]
    assert client.calls[3]["json"]["interactive"]["action"] == {
        "name": "flow",
        "parameters": {
            "flow_message_version": "3",
            "flow_token": "flow-token",
            "flow_id": "flow-123",
            "flow_cta": "Open flow",
            "flow_action": "navigate",
            "flow_action_payload": {
                "screen": "DETAILS",
                "data": {"customer_id": "cust-1"},
            },
        },
    }
    assert client.calls[4]["url"] == f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/123456789/media"
    assert client.calls[4]["data"] == {
        "messaging_product": "whatsapp",
        "type": "image/png",
    }
    assert client.calls[4]["files"]["file"] == ("poster.png", b"image-bytes", "image/png")
    assert "Content-Type" not in client.calls[4]["headers"]
    assert client.calls[5]["params"] == {"phone_number_id": "123456789"}
    assert client.calls[6]["method"] == "DELETE"


def test_meta_whatsapp_gateway_parses_status_events() -> None:
    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
    )

    events = gateway.parse_events(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.123",
                                        "status": "delivered",
                                        "recipient_id": "254712345678",
                                        "timestamp": "1712475856",
                                        "conversation": {
                                            "id": "conversation-1",
                                            "origin": {"type": "service"},
                                        },
                                        "pricing": {
                                            "pricing_model": "CBP",
                                            "billable": True,
                                            "category": "service",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert len(events) == 1
    assert events[0].channel == "whatsapp"
    assert events[0].provider == "meta"
    assert events[0].provider_message_id == "wamid.123"
    assert events[0].state == "delivered"
    assert events[0].metadata["conversation_id"] == "conversation-1"


def test_meta_whatsapp_gateway_parses_inbound_messages() -> None:
    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
    )

    messages = gateway.parse_inbound_messages(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "254700000000",
                                    "phone_number_id": "123456789",
                                },
                                "contacts": [
                                    {
                                        "wa_id": "254712345678",
                                        "profile": {"name": "Alice"},
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.text",
                                        "timestamp": "1712475856",
                                        "type": "text",
                                        "text": {"body": "Hello from Alice"},
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.image",
                                        "timestamp": "1712475857",
                                        "type": "image",
                                        "image": {
                                            "id": "media-1",
                                            "mime_type": "image/png",
                                            "caption": "Poster",
                                        },
                                        "context": {
                                            "message_id": "wamid.parent",
                                            "forwarded": True,
                                        },
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.location",
                                        "timestamp": "1712475858",
                                        "type": "location",
                                        "location": {
                                            "latitude": "-1.2921",
                                            "longitude": "36.8219",
                                            "name": "Nairobi",
                                        },
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.contacts",
                                        "timestamp": "1712475859",
                                        "type": "contacts",
                                        "contacts": [
                                            {
                                                "name": {
                                                    "formatted_name": "Bob Doe",
                                                    "first_name": "Bob",
                                                },
                                                "phones": [{"phone": "+254700111222"}],
                                            }
                                        ],
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.button",
                                        "timestamp": "1712475860",
                                        "type": "button",
                                        "button": {
                                            "text": "Confirm",
                                            "payload": "confirm-order",
                                        },
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.interactive",
                                        "timestamp": "1712475861",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "list_reply",
                                            "list_reply": {
                                                "id": "starter",
                                                "title": "Starter",
                                                "description": "Best for small teams",
                                            },
                                        },
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.reaction",
                                        "timestamp": "1712475862",
                                        "type": "reaction",
                                        "reaction": {
                                            "message_id": "wamid.parent",
                                            "emoji": "👍",
                                        },
                                    },
                                    {
                                        "from": "254712345678",
                                        "id": "wamid.unsupported",
                                        "timestamp": "1712475863",
                                        "type": "order",
                                    },
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert len(messages) == 8
    assert messages[0].message_type == "text"
    assert messages[0].text == "Hello from Alice"
    assert messages[0].profile_name == "Alice"
    assert messages[0].metadata["phone_number_id"] == "123456789"
    assert messages[1].message_type == "image"
    assert messages[1].media is not None
    assert messages[1].media.media_id == "media-1"
    assert messages[1].context_message_id == "wamid.parent"
    assert messages[1].forwarded is True
    assert messages[2].location is not None
    assert messages[2].location.latitude == -1.2921
    assert messages[3].contacts[0].name.formatted_name == "Bob Doe"
    assert messages[4].reply is not None
    assert messages[4].reply.reply_type == "button"
    assert messages[4].reply.payload == "confirm-order"
    assert messages[5].reply is not None
    assert messages[5].reply.reply_type == "list_reply"
    assert messages[5].reply.identifier == "starter"
    assert messages[6].reaction is not None
    assert messages[6].reaction.related_message_id == "wamid.parent"
    assert messages[7].message_type == "unsupported"
    assert messages[7].metadata["provider_message_type"] == "order"
    assert gateway.parse_inbound_message({"entry": []}) is None


def test_meta_signature_helpers_validate_payloads() -> None:
    payload = json.dumps({"entry": [{"id": "1"}]}).encode("utf-8")
    digest = hmac.new(b"app-secret", payload, hashlib.sha256).hexdigest()
    header = f"sha256={digest}"

    assert verify_meta_signature(payload, header, "app-secret") is True
    assert verify_meta_signature(payload, "sha256=bad", "app-secret") is False
    assert (
        resolve_meta_subscription_challenge(
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "1234",
            },
            "verify-me",
        )
        == "1234"
    )


def test_fastapi_meta_webhook_helper_verifies_signature_and_parses_events() -> None:
    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        app_secret="app-secret",
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.789",
                                    "status": "read",
                                    "recipient_id": "254712345678",
                                    "timestamp": "1712475856",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    digest = hmac.new(b"app-secret", payload_bytes, hashlib.sha256).hexdigest()
    request = FakeFastAPIRequest(
        headers={"x-hub-signature-256": f"sha256={digest}"},
        payload=payload_bytes,
    )

    async def run() -> None:
        events = await fastapi_parse_meta_delivery_events(
            request,
            gateway,
            require_signature=True,
        )
        assert len(events) == 1
        assert events[0].state == "read"

    asyncio.run(run())


def test_meta_webhook_helpers_parse_inbound_messages() -> None:
    gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        app_secret="app-secret",
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {
                                    "wa_id": "254712345678",
                                    "profile": {"name": "Alice"},
                                }
                            ],
                            "messages": [
                                {
                                    "from": "254712345678",
                                    "id": "wamid.inbound.1",
                                    "timestamp": "1712475856",
                                    "type": "text",
                                    "text": {"body": "Inbound hello"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    digest = hmac.new(b"app-secret", payload_bytes, hashlib.sha256).hexdigest()

    async def run() -> None:
        fastapi_messages = await fastapi_parse_meta_inbound_messages(
            FakeFastAPIRequest(
                headers={"x-hub-signature-256": f"sha256={digest}"},
                payload=payload_bytes,
            ),
            gateway,
            require_signature=True,
        )
        assert len(fastapi_messages) == 1
        assert fastapi_messages[0].text == "Inbound hello"

    asyncio.run(run())

    flask_messages = flask_parse_meta_inbound_messages(
        FakeFlaskRequest(
            headers={"X-Hub-Signature-256": f"sha256={digest}"},
            payload=payload_bytes,
            json_payload=payload,
        ),
        gateway,
        require_signature=True,
    )
    assert len(flask_messages) == 1
    assert flask_messages[0].message_id == "wamid.inbound.1"


def test_flask_onfon_webhook_helper_parses_delivery_reports() -> None:
    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
    )
    request = FakeFlaskRequest(
        args={
            "messageId": "msg-123",
            "mobile": "254712345678",
            "status": "DELIVRD",
            "doneDate": "2026-04-08 09:31",
        }
    )

    event = flask_parse_onfon_delivery_report(request, gateway)

    assert event is not None
    assert event.provider_message_id == "msg-123"
    assert event.state == "delivered"


def test_whatsapp_service_requires_gateway_configuration() -> None:
    messaging = MessagingClient()

    with pytest.raises(ConfigurationError):
        messaging.whatsapp.send_text(
            WhatsAppTextRequest(recipient="254712345678", text="Hello over WhatsApp")
        )
