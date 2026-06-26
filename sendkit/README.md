# `sendkit`

Modular Python SDK for WhatsApp and bulk SMS providers.

Python `>=3.11` is required. SendKit ships **sync and async** clients backed by
`httpx`, and is designed for services, workers, and serverless messaging flows.

Use `sendkit` when you want direct provider wrappers:

- Meta WhatsApp Cloud API
- Onfon bulk SMS
- Africa's Talking SMS

Each provider exposes a synchronous client and an asynchronous `Async*`
counterpart that share the same request models, payload building, and response
parsing — one definition, two execution models.

## Install

```bash
pip install noria-sendkit
```

The distribution is published as `noria-sendkit`; the import package is `sendkit`.

## Imports

Import the whole package:

```python
from sendkit import (
    AfricasTalkingSmsClient,
    MetaWhatsAppClient,
    OnfonSmsClient,
)
```

Or import the async clients:

```python
from sendkit import (
    AsyncAfricasTalkingSmsClient,
    AsyncMetaWhatsAppClient,
    AsyncOnfonSmsClient,
)
```

Modular subpackages are also available:

- `sendkit` — everything
- `sendkit.sms` — SMS clients and models
- `sendkit.whatsapp` — WhatsApp client and models

## Quick Start

### WhatsApp

```python
from sendkit import MetaWhatsAppClient, WhatsAppTextRequest

whatsapp = MetaWhatsAppClient(
    access_token="...",
    phone_number_id="...",
)

with whatsapp:
    whatsapp.send_text(
        WhatsAppTextRequest(recipient="254700123456", text="Hello from Noria")
    )
```

The async client mirrors the sync API:

```python
import asyncio

from sendkit import AsyncMetaWhatsAppClient, WhatsAppTextRequest


async def main() -> None:
    async with AsyncMetaWhatsAppClient(
        access_token="...",
        phone_number_id="...",
    ) as whatsapp:
        await whatsapp.send_text(
            WhatsAppTextRequest(recipient="254700123456", text="Hello from Noria")
        )


asyncio.run(main())
```

### Onfon SMS

```python
from sendkit import OnfonSmsClient, SmsMessage, SmsSendRequest

sms = OnfonSmsClient(
    access_key="...",
    api_key="...",
    client_id="...",
    default_sender_id="NORIALABS",
)

sms.send(
    SmsSendRequest(
        messages=[
            SmsMessage(recipient="254700123456", text="Your OTP is 123456", reference="otp-1"),
        ]
    )
)
```

### Africa's Talking SMS

```python
from sendkit import AfricasTalkingSmsClient, SmsMessage, SmsSendRequest

sms = AfricasTalkingSmsClient(
    api_key="...",
    username="...",
    default_sender_id="NORIALABS",
)

sms.send(
    SmsSendRequest(
        messages=[
            SmsMessage(recipient="+254700123456", text="Your OTP is 123456", reference="otp-1"),
        ]
    )
)
```

## Provider Coverage

| Provider | Capabilities |
| --- | --- |
| Meta WhatsApp | Text, templates, media by id or URL, media upload/get/delete, location, contacts, reactions, interactive buttons/lists, catalog, single product, product list, flows, mark-read, typing indicator, template management, delivery parsing, inbound parsing |
| Onfon SMS | Bulk SMS send, scheduled SMS, Unicode/flash flags, balance, groups, templates, delivery report parsing |
| Africa's Talking SMS | Bulk SMS send, premium SMS reply, incoming message fetch, subscription create/delete, balance, delivery report parsing |

Non-SMS Africa's Talking products such as Airtime, Voice, USSD, Payments, and
Data Bundles are intentionally outside the current SMS scope.

## Shared Transport

Every provider client accepts the same transport options:

- `client`: a custom `httpx.Client` / `httpx.AsyncClient`
- `timeout_seconds`: request timeout
- `default_headers`: extra default headers
- `retry`: a `RetryPolicy` (or `False` to disable)
- `hooks`: `Hooks(before_request=..., after_response=..., on_error=...)`

Per-request options are passed via `RequestOptions`:

- `headers`
- `timeout_seconds`
- `retry`

```python
from sendkit import Hooks, OnfonSmsClient, RetryPolicy

sms = OnfonSmsClient(
    access_key="access-key",
    api_key="api-key",
    client_id="client-id",
    timeout_seconds=15.0,
    retry=RetryPolicy(
        max_attempts=3,
        retry_methods=("GET", "POST"),
        retry_on_statuses=(429, 500, 502, 503, 504),
        retry_on_network_error=True,
        base_delay_seconds=0.25,
    ),
    hooks=Hooks(
        before_request=lambda ctx: ctx.headers.__setitem__("x-trace-id", "trace-123"),
    ),
)
```

## Construction From Environment

Each client exposes a `from_env(...)` classmethod.

```python
sms = OnfonSmsClient.from_env()
whatsapp = MetaWhatsAppClient.from_env()
at = AfricasTalkingSmsClient.from_env()
```

### Onfon env vars

- `ONFON_ACCESS_KEY`
- `ONFON_API_KEY`
- `ONFON_CLIENT_ID`
- `ONFON_SENDER_ID`
- `ONFON_BASE_URL`
- `ONFON_TIMEOUT_SECONDS`

### Meta WhatsApp env vars

- `META_WHATSAPP_ACCESS_TOKEN`
- `META_WHATSAPP_PHONE_NUMBER_ID`
- `META_WHATSAPP_WHATSAPP_BUSINESS_ACCOUNT_ID`
- `META_WHATSAPP_APP_SECRET`
- `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN`
- `META_WHATSAPP_API_VERSION`
- `META_WHATSAPP_BASE_URL`
- `META_WHATSAPP_TIMEOUT_SECONDS`

`whatsapp_business_account_id` is required only for template management methods.

### Africa's Talking env vars

- `AFRICASTALKING_API_KEY`
- `AFRICASTALKING_USERNAME`
- `AFRICASTALKING_SENDER_ID`
- `AFRICASTALKING_BASE_URL`
- `AFRICASTALKING_TIMEOUT_SECONDS`

Fallback names are also accepted: `AFRICAS_TALKING_API_KEY`,
`AFRICAS_TALKING_USERNAME`, `AFRICAS_TALKING_SENDER_ID`,
`AFRICAS_TALKING_BASE_URL`.

## WhatsApp: Meta Cloud API

### WhatsApp Method Reference

| Method | Purpose |
| --- | --- |
| `send_text(request, options=None)` | Send text messages with optional URL preview |
| `send_template(request, options=None)` | Send approved template messages |
| `send_media(request, options=None)` | Send image, audio, document, sticker, or video by media id or URL |
| `send_location(request, options=None)` | Send a location pin |
| `send_contacts(request, options=None)` | Send one or more contacts |
| `send_reaction(request, options=None)` | React to an existing message |
| `send_interactive(request, options=None)` | Send reply-button or list interactive messages |
| `send_catalog(request, options=None)` | Send catalog messages |
| `send_product(request, options=None)` | Send a single-product message |
| `send_product_list(request, options=None)` | Send a multi-product list |
| `send_flow(request, options=None)` | Send a WhatsApp Flow interactive message |
| `mark_message_read(request, options=None)` | Mark an inbound message as read |
| `send_typing_indicator(request, options=None)` | Mark as read and show a typing indicator |
| `upload_media(request, options=None)` | Upload media bytes to Meta |
| `get_media(media_id, options=None)` | Get media metadata and download URL |
| `delete_media(media_id, options=None)` | Delete uploaded media |
| `list_templates(request=None, options=None)` | List templates for a WABA |
| `get_template(template_id, fields=None, options=None)` | Fetch one template |
| `create_template(request, options=None)` | Create a template |
| `update_template(template_id, request, options=None)` | Update a template |
| `delete_template(request, options=None)` | Delete a template by name, id, or ids |
| `parse_events(payload)` | Parse delivery/read/failed webhook statuses |
| `parse_inbound_messages(payload)` | Parse inbound messages |
| `parse_event(payload)` | Return the first parsed delivery event, or `None` |
| `parse_inbound_message(payload)` | Return the first parsed inbound message, or `None` |

### Text

```python
from sendkit import WhatsAppTextRequest

whatsapp.send_text(
    WhatsAppTextRequest(
        recipient="254700123456",
        text="Plain text message",
        preview_url=True,
        reply_to_message_id="wamid.previous",
    )
)
```

### Templates

Template messages support text, media, and button parameters. For media headers
pass a parameter of type `image`, `video`, or `document` and either a `value`
(an uploaded media id) or a provider-specific object via `provider_options`.

```python
from sendkit import (
    WhatsAppTemplateComponent,
    WhatsAppTemplateParameter,
    WhatsAppTemplateRequest,
)

whatsapp.send_template(
    WhatsAppTemplateRequest(
        recipient="254700123456",
        template_name="order_update",
        language_code="en",
        components=[
            WhatsAppTemplateComponent(
                type="header",
                parameters=[
                    WhatsAppTemplateParameter(
                        type="document",
                        provider_options={
                            "document": {"id": "media-id", "filename": "invoice.pdf"}
                        },
                    )
                ],
            ),
            WhatsAppTemplateComponent(
                type="body",
                parameters=[
                    WhatsAppTemplateParameter(type="text", value="NORIA-123"),
                    WhatsAppTemplateParameter(type="text", value="Ready for pickup"),
                ],
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
```

### Media And Attachments

Send media by public URL, by uploaded id, or upload bytes first and use the
returned media id.

```python
from sendkit import WhatsAppMediaRequest, WhatsAppMediaUploadRequest

whatsapp.send_media(
    WhatsAppMediaRequest(
        recipient="254700123456",
        media_type="image",
        link="https://example.com/product.jpg",
        caption="Preview",
    )
)

uploaded = whatsapp.upload_media(
    WhatsAppMediaUploadRequest(
        filename="menu.pdf",
        mime_type="application/pdf",
        content=b"file-bytes",
    )
)

whatsapp.send_media(
    WhatsAppMediaRequest(
        recipient="254700123456",
        media_type="document",
        media_id=uploaded.media_id,
        filename="menu.pdf",
    )
)

whatsapp.get_media(uploaded.media_id)
whatsapp.delete_media(uploaded.media_id)
```

Supported media types: `image`, `audio`, `document`, `sticker`, `video`.

### Location, Contacts, And Reactions

```python
from sendkit import (
    WhatsAppContact,
    WhatsAppContactName,
    WhatsAppContactPhone,
    WhatsAppContactsRequest,
    WhatsAppLocationRequest,
    WhatsAppReactionRequest,
)

whatsapp.send_location(
    WhatsAppLocationRequest(
        recipient="254700123456",
        latitude=-1.286389,
        longitude=36.817223,
        name="Nairobi Office",
        address="Nairobi, Kenya",
    )
)

whatsapp.send_contacts(
    WhatsAppContactsRequest(
        recipient="254700123456",
        contacts=[
            WhatsAppContact(
                name=WhatsAppContactName(formatted_name="Noria Support", first_name="Noria"),
                phones=[WhatsAppContactPhone(phone="+254700000000", type="WORK")],
            )
        ],
    )
)

whatsapp.send_reaction(
    WhatsAppReactionRequest(recipient="254700123456", message_id="wamid.inbound", emoji="👍")
)
```

### Interactive, Catalog, Product, And Flow Messages

```python
from sendkit import (
    WhatsAppFlowMessageRequest,
    WhatsAppInteractiveButton,
    WhatsAppInteractiveHeader,
    WhatsAppInteractiveRequest,
    WhatsAppInteractiveRow,
    WhatsAppInteractiveSection,
    WhatsAppProductItem,
    WhatsAppProductListRequest,
    WhatsAppProductSection,
)

whatsapp.send_interactive(
    WhatsAppInteractiveRequest(
        recipient="254700123456",
        interactive_type="button",
        body_text="Choose one",
        buttons=[
            WhatsAppInteractiveButton(identifier="yes", title="Yes"),
            WhatsAppInteractiveButton(identifier="no", title="No"),
        ],
    )
)

whatsapp.send_interactive(
    WhatsAppInteractiveRequest(
        recipient="254700123456",
        interactive_type="list",
        body_text="Choose a product",
        button_text="View options",
        sections=[
            WhatsAppInteractiveSection(
                title="Products",
                rows=[
                    WhatsAppInteractiveRow(identifier="sku-1", title="Starter"),
                    WhatsAppInteractiveRow(identifier="sku-2", title="Pro"),
                ],
            )
        ],
    )
)

whatsapp.send_product_list(
    WhatsAppProductListRequest(
        recipient="254700123456",
        catalog_id="catalog-1",
        header=WhatsAppInteractiveHeader(type="text", text="Featured"),
        sections=[
            WhatsAppProductSection(
                title="Top Picks",
                product_items=[WhatsAppProductItem(product_retailer_id="sku-1")],
            )
        ],
    )
)

whatsapp.send_flow(
    WhatsAppFlowMessageRequest(
        recipient="254700123456",
        flow_cta="Start",
        flow_id="flow-1",
        flow_action="navigate",
    )
)
```

### Read Receipts And Typing Indicator

```python
from sendkit import WhatsAppReadRequest

whatsapp.mark_message_read(WhatsAppReadRequest(message_id="wamid.inbound"))
whatsapp.send_typing_indicator(WhatsAppReadRequest(message_id="wamid.inbound"))
```

### Template Management

```python
from sendkit import (
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDeleteRequest,
    WhatsAppTemplateListRequest,
    WhatsAppTemplateUpdateRequest,
)

result = whatsapp.list_templates(
    WhatsAppTemplateListRequest(limit=20, status=["approved"])
)

whatsapp.get_template("template-id")

whatsapp.create_template(
    WhatsAppTemplateCreateRequest(
        name="order_update",
        language="en_US",
        category="utility",
    )
)

whatsapp.update_template("template-id", WhatsAppTemplateUpdateRequest(category="utility"))
whatsapp.delete_template(WhatsAppTemplateDeleteRequest(template_id="template-id"))
```

### WhatsApp Webhooks

```python
delivery_events = whatsapp.parse_events(meta_webhook_payload)
inbound_messages = whatsapp.parse_inbound_messages(meta_webhook_payload)
```

`parse_inbound_messages` supports inbound text, media, location, contacts,
button replies, interactive replies, reactions, and unsupported message
fallback metadata.

## SMS: Shared Request Shape

All SMS providers use the shared `SmsSendRequest`:

```python
from datetime import datetime

from sendkit import SmsMessage, SmsSendRequest

sms.send(
    SmsSendRequest(
        sender_id="NORIALABS",
        messages=[
            SmsMessage(
                recipient="254700123456",
                text="Hello",
                reference="internal-id",
                metadata={"account_id": "acct_1"},
            )
        ],
        schedule_at=datetime(2026, 6, 26, 9, 0, 0),
        is_unicode=False,
        is_flash=False,
        provider_options={},
    )
)
```

`provider_options` is passed through to the underlying provider payload when you
need provider-specific fields.

## SMS: Onfon

### Onfon Method Reference

| Method | Purpose |
| --- | --- |
| `send(request, options=None)` | Send one or more SMS messages |
| `get_balance(options=None)` | Read SMS balance |
| `list_groups(options=None)` | List contact groups |
| `create_group(request, options=None)` | Create a contact group |
| `update_group(group_id, request, options=None)` | Update a contact group |
| `delete_group(group_id, options=None)` | Delete a contact group |
| `list_templates(options=None)` | List SMS templates |
| `create_template(request, options=None)` | Create an SMS template |
| `update_template(template_id, request, options=None)` | Update an SMS template |
| `delete_template(template_id, options=None)` | Delete an SMS template |
| `parse_delivery_report(payload)` | Parse delivery-report callbacks |

```python
from sendkit import SmsGroupUpsertRequest, SmsMessage, SmsSendRequest, SmsTemplateUpsertRequest

result = sms.send(
    SmsSendRequest(
        sender_id="NORIALABS",
        messages=[
            SmsMessage(recipient="254700123456", text="Hello there", reference="msg-1"),
            SmsMessage(recipient="254711111111", text="Hello again", reference="msg-2"),
        ],
        is_unicode=False,
    )
)

sms.get_balance()

group = sms.create_group(SmsGroupUpsertRequest(name="VIP Customers"))
sms.update_group(group.resource_id, SmsGroupUpsertRequest(name="Priority Customers"))
sms.delete_group(group.resource_id)

template = sms.create_template(SmsTemplateUpsertRequest(name="otp", body="Your OTP is {{1}}"))
sms.update_template(template.resource_id, SmsTemplateUpsertRequest(name="otp", body="Use code {{1}}"))
sms.delete_template(template.resource_id)

report = sms.parse_delivery_report(
    {"messageId": "abc123", "mobile": "254700123456", "status": "Delivered"}
)
```

## SMS: Africa's Talking

Use `AFRICASTALKING_SANDBOX_SMS_BASE_URL` for sandbox clients:

```python
from sendkit import AFRICASTALKING_SANDBOX_SMS_BASE_URL, AfricasTalkingSmsClient

sandbox_sms = AfricasTalkingSmsClient(
    api_key="...",
    username="sandbox",
    base_url=AFRICASTALKING_SANDBOX_SMS_BASE_URL,
)
```

### Africa's Talking Method Reference

| Method | Purpose |
| --- | --- |
| `send(request, options=None)` | Send normal bulk SMS |
| `send_premium(request, options=None)` | Send premium SMS replies using keyword and link id |
| `fetch_messages(request=None, options=None)` | Fetch incoming SMS messages |
| `create_subscription(request, options=None)` | Opt a phone number into a premium SMS subscription |
| `delete_subscription(request, options=None)` | Remove a premium SMS subscription |
| `get_balance(options=None)` | Read account balance |
| `parse_delivery_report(payload)` | Parse delivery-report callbacks |

The client groups messages by text because Africa's Talking accepts one message
body per request and many recipients.

```python
from sendkit import (
    AfricasTalkingFetchMessagesRequest,
    AfricasTalkingPremiumSmsRequest,
    AfricasTalkingSubscriptionRequest,
    SmsMessage,
    SmsSendRequest,
)

sms.send(
    SmsSendRequest(
        sender_id="NORIALABS",
        messages=[
            SmsMessage(recipient="+254700123456", text="Hello", reference="msg-1"),
            SmsMessage(recipient="+254711111111", text="Hello", reference="msg-2"),
        ],
        provider_options={"enqueue": "1"},
    )
)

sms.send_premium(
    AfricasTalkingPremiumSmsRequest(
        recipient="+254700123456",
        short_code="22384",
        keyword="NORIA",
        link_id="link-id-from-inbound-message",
        text="Thanks for subscribing",
        retry_duration_in_hours=2,
    )
)

inbox = sms.fetch_messages(AfricasTalkingFetchMessagesRequest(last_received_id=42))
for message in inbox.messages:
    print(message.provider_message_id, message.sender, message.text)

sms.create_subscription(
    AfricasTalkingSubscriptionRequest(
        phone_number="+254700123456", short_code="22384", keyword="NORIA"
    )
)
sms.delete_subscription(
    AfricasTalkingSubscriptionRequest(
        phone_number="+254700123456", short_code="22384", keyword="NORIA"
    )
)

sms.get_balance()

event = sms.parse_delivery_report(
    {
        "id": "at-message-id",
        "phoneNumber": "+254700123456",
        "status": "Success",
        "networkCode": "63902",
        "retryCount": "0",
    }
)
```

## Webhooks

### Meta Verification Challenge

```python
from sendkit import resolve_meta_subscription_challenge

challenge = resolve_meta_subscription_challenge(
    {
        "hub.mode": "subscribe",
        "hub.verify_token": "verify-me",
        "hub.challenge": "12345",
    },
    "verify-me",
)
```

### Meta Signature Verification

```python
from sendkit import require_valid_meta_signature

require_valid_meta_signature(raw_body, signature_header, app_secret)
```

### SMS Delivery Reports

```python
from sendkit import parse_africastalking_sms_delivery_report, parse_onfon_delivery_report

onfon_event = parse_onfon_delivery_report(query_params, onfon_client)
at_event = parse_africastalking_sms_delivery_report(body, africastalking_client)
```

## Errors

Exported errors:

- `SendKitError`
- `ConfigurationError`
- `ApiError`
- `ProviderError`
- `NetworkError`
- `TimeoutError`
- `WebhookVerificationError`

Provider errors include provider response details where available.

```python
from sendkit import ProviderError, SmsSendRequest

try:
    sms.send(SmsSendRequest(messages=[...]))
except ProviderError as error:
    print(error.provider, error.error_code, error.response_body)
```

## Lifecycle

Sync clients are context managers and expose `close()`; async clients are async
context managers and expose `aclose()`. When you pass your own `httpx` client,
SendKit will not close it for you.

```python
with OnfonSmsClient(access_key="...", api_key="...", client_id="...") as sms:
    sms.get_balance()

async with AsyncOnfonSmsClient(access_key="...", api_key="...", client_id="...") as sms:
    await sms.get_balance()
```

## Runtime Exports

Root constant exports:

- `ONFON_BASE_URL`
- `ONFON_SMS_BASE_URL`
- `AFRICASTALKING_SMS_BASE_URL`
- `AFRICASTALKING_SANDBOX_SMS_BASE_URL`
- `META_GRAPH_BASE_URL`
- `META_GRAPH_API_VERSION`

Provider clients, request/result models, transport types (`RequestOptions`,
`RetryPolicy`, `Hooks`, `DeliveryEvent`, `DeliveryState`, `MessageChannel`), and
webhook helpers are all available from the top-level `sendkit` package.
