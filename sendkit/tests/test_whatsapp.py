from __future__ import annotations

import pytest
from support import FakeAsyncClient, FakeSyncClient, json_response, run

from sendkit import (
    META_GRAPH_API_VERSION,
    AsyncMetaWhatsAppClient,
    ConfigurationError,
    MetaWhatsAppClient,
    WhatsAppFlowMessageRequest,
    WhatsAppInteractiveButton,
    WhatsAppInteractiveHeader,
    WhatsAppInteractiveRequest,
    WhatsAppMediaRequest,
    WhatsAppMediaUploadRequest,
    WhatsAppProductItem,
    WhatsAppProductListRequest,
    WhatsAppProductSection,
    WhatsAppReadRequest,
    WhatsAppTemplateComponent,
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDeleteRequest,
    WhatsAppTemplateListRequest,
    WhatsAppTemplateParameter,
    WhatsAppTemplateRequest,
    WhatsAppTemplateUpdateRequest,
    WhatsAppTextRequest,
)

CLIENTS = [(MetaWhatsAppClient, False), (AsyncMetaWhatsAppClient, True)]


def _handler(call):
    url = call["url"]
    method = call["method"]
    body = call.get("json")

    if url.endswith("/messages") and isinstance(body, dict) and body.get("status") == "read":
        return json_response({"success": True})
    if url.endswith("/messages"):
        return json_response(
            {
                "contacts": [{"wa_id": "254700123456"}],
                "messages": [{"id": "wamid.1", "message_status": "accepted"}],
            }
        )
    if url.endswith("/message_templates") and method == "GET":
        return json_response(
            {
                "data": [
                    {"id": "tmpl-1", "name": "welcome", "language": "en_US", "category": "UTILITY"}
                ],
                "paging": {"cursors": {"before": "a", "after": "b"}},
                "summary": {"total_count": 1},
            }
        )
    if url.endswith("/message_templates") and method == "POST":
        return json_response({"id": "tmpl-1", "status": "APPROVED"})
    if url.endswith("/message_templates") and method == "DELETE":
        return json_response({"success": True})
    if url.endswith("/tmpl-1") and method == "GET":
        return json_response(
            {"id": "tmpl-1", "name": "welcome", "language": "en_US", "category": "UTILITY"}
        )
    if url.endswith("/tmpl-1") and method == "POST":
        return json_response({"id": "tmpl-1", "status": "APPROVED"})
    if url.endswith("/media") and method == "POST":
        return json_response({"id": "media-1"})
    if url.endswith("/media-1") and method == "GET":
        return json_response(
            {
                "id": "media-1",
                "url": "https://example.com/media",
                "mime_type": "application/pdf",
                "file_size": 42,
            }
        )
    if url.endswith("/media-1") and method == "DELETE":
        return json_response({"success": True})
    return json_response({"success": True})


def _make(cls, is_async):
    fake = (FakeAsyncClient if is_async else FakeSyncClient)(_handler)
    client = cls(
        access_token="token",
        phone_number_id="123456789",
        whatsapp_business_account_id="9988776655",
        client=fake,
    )
    return client, fake


def test_whatsapp_validates_required_config():
    with pytest.raises(ConfigurationError):
        MetaWhatsAppClient(access_token="", phone_number_id="123456789")


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_whatsapp_sends_and_template_payload(cls, is_async):
    client, fake = _make(cls, is_async)

    assert META_GRAPH_API_VERSION == "v25.0"

    text = run(
        client.send_text(
            WhatsAppTextRequest(recipient="254700123456", text="hello", preview_url=True)
        )
    )
    assert text.messages[0].provider_message_id == "wamid.1"
    assert (
        fake.calls[0]["url"]
        == f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/123456789/messages"
    )

    template = run(
        client.send_template(
            WhatsAppTemplateRequest(
                recipient="254700123456",
                template_name="order_update",
                language_code="en_US",
                components=[
                    WhatsAppTemplateComponent(
                        type="header",
                        parameters=[
                            WhatsAppTemplateParameter(type="document", value="media-doc-1")
                        ],
                    ),
                    WhatsAppTemplateComponent(
                        type="body",
                        parameters=[WhatsAppTemplateParameter(type="text", value="NORIA-123")],
                    ),
                    WhatsAppTemplateComponent(
                        type="button",
                        sub_type="quick_reply",
                        index=0,
                        parameters=[WhatsAppTemplateParameter(type="payload", value="track-order")],
                    ),
                ],
            )
        )
    )
    assert template.accepted is True
    assert fake.calls[-1]["json"]["template"]["components"] == [
        {"type": "header", "parameters": [{"type": "document", "document": {"id": "media-doc-1"}}]},
        {"type": "body", "parameters": [{"type": "text", "text": "NORIA-123"}]},
        {
            "type": "button",
            "sub_type": "quick_reply",
            "index": 0,
            "parameters": [{"type": "payload", "payload": "track-order"}],
        },
    ]

    media = run(
        client.send_media(
            WhatsAppMediaRequest(
                recipient="254700123456",
                media_type="document",
                link="https://example.com/menu.pdf",
                caption="Menu",
                filename="menu.pdf",
            )
        )
    )
    assert media.accepted is True
    assert fake.calls[-1]["json"]["document"] == {
        "link": "https://example.com/menu.pdf",
        "caption": "Menu",
        "filename": "menu.pdf",
    }

    interactive = run(
        client.send_interactive(
            WhatsAppInteractiveRequest(
                recipient="254700123456",
                interactive_type="button",
                body_text="Choose",
                buttons=[WhatsAppInteractiveButton(identifier="yes", title="Yes")],
            )
        )
    )
    assert interactive.accepted is True

    product_list = run(
        client.send_product_list(
            WhatsAppProductListRequest(
                recipient="254700123456",
                catalog_id="catalog-1",
                header=WhatsAppInteractiveHeader(type="text", text="Featured"),
                sections=[
                    WhatsAppProductSection(
                        title="Top",
                        product_items=[WhatsAppProductItem(product_retailer_id="sku-1")],
                    )
                ],
            )
        )
    )
    assert product_list.messages[0].provider_message_id == "wamid.1"

    flow = run(
        client.send_flow(
            WhatsAppFlowMessageRequest(
                recipient="254700123456", flow_cta="Start", flow_id="flow-1"
            )
        )
    )
    assert flow.messages[0].provider_message_id == "wamid.1"


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_whatsapp_read_typing_templates_media(cls, is_async):
    client, fake = _make(cls, is_async)

    read = run(client.mark_message_read(WhatsAppReadRequest(message_id="wamid.inbound.1")))
    assert read.success is True
    assert fake.calls[-1]["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.inbound.1",
    }

    typing = run(client.send_typing_indicator(WhatsAppReadRequest(message_id="wamid.inbound.2")))
    assert typing.message_id == "wamid.inbound.2"
    assert fake.calls[-1]["json"] == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.inbound.2",
        "typing_indicator": {"type": "text"},
    }

    templates = run(client.list_templates(WhatsAppTemplateListRequest(limit=10)))
    assert templates.templates[0].template_id == "tmpl-1"
    assert fake.calls[-1]["params"]["limit"] == "10"

    assert run(client.get_template("tmpl-1")).name == "welcome"
    assert (
        run(
            client.create_template(
                WhatsAppTemplateCreateRequest(name="welcome", language="en_US", category="utility")
            )
        ).template_id
        == "tmpl-1"
    )
    update_request = WhatsAppTemplateUpdateRequest(category="utility")
    updated = run(client.update_template("tmpl-1", update_request))
    assert updated.success is True
    deleted = run(client.delete_template(WhatsAppTemplateDeleteRequest(template_id="tmpl-1")))
    assert deleted.deleted is True

    uploaded = run(
        client.upload_media(
            WhatsAppMediaUploadRequest(
                filename="menu.pdf", mime_type="application/pdf", content=b"pdf"
            )
        )
    )
    assert uploaded.media_id == "media-1"
    assert fake.calls[-1]["files"]["file"][0] == "menu.pdf"
    assert fake.calls[-1]["data"]["type"] == "application/pdf"

    assert run(client.get_media("media-1")).file_size == 42
    assert run(client.delete_media("media-1")).deleted is True


@pytest.mark.parametrize(("cls", "is_async"), CLIENTS)
def test_whatsapp_parses_webhooks(cls, is_async):
    client, _fake = _make(cls, is_async)

    events = client.parse_events(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.status.1",
                                        "status": "delivered",
                                        "recipient_id": "254700123456",
                                        "timestamp": "1710000000",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert events[0].provider_message_id == "wamid.status.1"
    assert events[0].state == "delivered"

    inbound = client.parse_inbound_messages(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "254700999999",
                                    "phone_number_id": "123456789",
                                },
                                "contacts": [
                                    {"wa_id": "254700123456", "profile": {"name": "Alice"}}
                                ],
                                "messages": [
                                    {
                                        "from": "254700123456",
                                        "id": "wamid.inbound.1",
                                        "type": "text",
                                        "timestamp": "1710000001",
                                        "text": {"body": "Hi"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert inbound[0].message_id == "wamid.inbound.1"
    assert inbound[0].text == "Hi"
    assert inbound[0].profile_name == "Alice"
