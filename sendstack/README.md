# `sendstack`

Official Python SDK for the SendStack messaging API.

Built on `httpx`, it ships both a synchronous client (`Sendstack`) and an
asynchronous client (`AsyncSendstack`) covering the SendStack developer API.

Use it for:

- transactional and scheduled email, SMS, and WhatsApp
- batch email, SMS, and WhatsApp
- reusable attachment uploads
- sending domains
- WhatsApp Business senders and SMS sender-ID provisioning
- email, SMS, and WhatsApp templates (with rendered previews)
- webhook endpoints and webhook event retries
- suppression lists
- billing: credits, checkout, and payment/purchase history

Python `>=3.11` is required.

## Install

```bash
pip install sendstack
```

For local development:

```bash
uv sync --extra dev
```

## Quick Start

### Sync

```python
import os

from sendstack import Sendstack, RequestOptions

token = os.environ["SENDSTACK_TOKEN"]

client = Sendstack(token)

message = client.emails.send(
    {
        "from": "Noria <hello@example.com>",
        "to": "friend@example.com",
        "subject": "Hello from SendStack",
        "html": "<p>Your email pipeline is working.</p>",
        "text": "Your email pipeline is working.",
    },
    RequestOptions(idempotency_key="welcome-email-1"),
)

print(message["id"], message["status"])
```

`Sendstack` opens an `httpx.Client` for you. Close it when you are done, or use
it as a context manager:

```python
with Sendstack(token) as client:
    client.emails.send({"from": "hello@example.com", "to": "friend@example.com", "text": "Hi"})
```

### Async

```python
import asyncio
import os

from sendstack import AsyncSendstack, RequestOptions


async def main() -> None:
    async with AsyncSendstack(os.environ["SENDSTACK_TOKEN"]) as client:
        message = await client.emails.send(
            {
                "from": "Noria <hello@example.com>",
                "to": "friend@example.com",
                "subject": "Hello from SendStack",
                "text": "Your async pipeline is working.",
            },
            RequestOptions(idempotency_key="welcome-email-1"),
        )
        print(message["id"], message["status"])


asyncio.run(main())
```

Every example below works on both clients. On `Sendstack` a method returns the
decoded payload; on `AsyncSendstack` the same call returns a coroutine you
`await`.

### Base URL

The SDK defaults to `https://sendstack.norialabs.com/api/v1` (the versioned API
base). Override `base_url` to point at another environment — include the
`/api/v1` version segment, since resource paths (e.g. `/emails`) are sent
relative to whatever base you provide:

```python
client = Sendstack(token, base_url="https://staging.norialabs.com/api/v1")
```

## Docs Split

This README is the package guide: install, initialization, SDK methods, request
options, errors, and examples.

The SaaS docs remain the canonical source for product/API behavior: account
setup, API tokens, domain verification, DNS records, webhook event catalogs,
deliverability concepts, provider behavior, dashboard workflows, and the raw
HTTP API reference. Current live SaaS docs are at
`https://sendstack.norialabs.com/api/docs`.

## Auth

The API uses bearer auth:

```http
Authorization: Bearer <token>
```

Passing a token as the first argument configures that header automatically:

```python
client = Sendstack("mlr_live_...")
```

You can also pass a custom auth strategy. Tokens may be static or resolved per
request (sync or async callables both work):

```python
from sendstack import BearerAuthStrategy, Sendstack

client = Sendstack(
    base_url="https://sendstack.norialabs.com/api/v1",
    auth=BearerAuthStrategy(token=lambda context: get_fresh_token()),
)
```

Use `HeadersAuthStrategy` when the target environment expects custom headers,
and `RequestOptions(authenticated=False)` to strip auth for a single call.

## Method Reference

| SDK method | HTTP route | Returns |
| --- | --- | --- |
| `attachments.upload(payload, options=None)` | `POST /attachments` | `UploadedAttachment` |
| `emails.send(payload, options=None)` | `POST /emails` | `SendEmailResult` |
| `emails.send_batch(payload, options=None)` | `POST /emails/batch` | `SendEmailBatchResult` |
| `emails.list(options=None, *, limit=None, cursor=None, status=None)` | `GET /emails` | `CursorPage` |
| `emails.get(message_id, options=None)` | `GET /emails/{id}` | `EmailMessage` |
| `emails.events(message_id, options=None)` | `GET /emails/{id}/events` | `CursorPage` |
| `emails.cancel(message_id, options=None)` | `POST /emails/{id}/cancel` | `EmailMessage` |
| `emails.requeue(message_id, options=None)` | `POST /emails/{id}/requeue` | `EmailMessage` |
| `sms.send(payload, options=None)` | `POST /sms` | `SendSmsResult` |
| `sms.send_batch(payload, options=None)` | `POST /sms/batch` | `SendSmsBatchResult` |
| `sms.list(options=None, *, limit=None, cursor=None, status=None)` | `GET /sms` | `CursorPage` |
| `sms.get(message_id, options=None)` | `GET /sms/{id}` | `SmsMessage` |
| `sms.events(message_id, options=None)` | `GET /sms/{id}/events` | `CursorPage` |
| `sms.cancel(message_id, options=None)` | `POST /sms/{id}/cancel` | `SmsMessage` |
| `sms.requeue(message_id, options=None)` | `POST /sms/{id}/requeue` | `SmsMessage` |
| `whatsapp.send(payload, options=None)` | `POST /whatsapp` | `SendWhatsAppResult` |
| `whatsapp.send_batch(payload, options=None)` | `POST /whatsapp/batch` | `SendWhatsAppBatchResult` |
| `whatsapp.list(options=None, *, limit=None, cursor=None, status=None)` | `GET /whatsapp` | `CursorPage` |
| `whatsapp.get(message_id, options=None)` | `GET /whatsapp/{id}` | `WhatsAppMessage` |
| `whatsapp.events(message_id, options=None)` | `GET /whatsapp/{id}/events` | `CursorPage` |
| `whatsapp.cancel(message_id, options=None)` | `POST /whatsapp/{id}/cancel` | `WhatsAppMessage` |
| `whatsapp.requeue(message_id, options=None)` | `POST /whatsapp/{id}/requeue` | `WhatsAppMessage` |
| `whatsapp_senders.list(options=None)` | `GET /whatsapp/senders` | `CursorPage` |
| `whatsapp_senders.create(payload, options=None)` | `POST /whatsapp/senders` | `WhatsAppSenderRef` |
| `whatsapp_senders.get(sender_id, options=None)` | `GET /whatsapp/senders/{id}` | `WhatsAppSender` |
| `whatsapp_senders.set_default(sender_id, options=None)` | `POST /whatsapp/senders/{id}/default` | `WhatsAppSenderRef` |
| `whatsapp_senders.remove(sender_id, options=None)` | `DELETE /whatsapp/senders/{id}` | `None` |
| `domains.create(payload, options=None)` | `POST /domains` | `Domain` |
| `domains.list(options=None)` | `GET /domains` | `CursorPage` |
| `domains.get(domain_id, options=None)` | `GET /domains/{id}` | `Domain` |
| `domains.verify(domain_id, options=None)` | `POST /domains/{id}/verify` | `Domain` |
| `templates.create(payload, options=None)` | `POST /templates` | `EmailTemplate` |
| `templates.list(options=None)` | `GET /templates` | `CursorPage` |
| `templates.get(template_id, options=None)` | `GET /templates/{id}` | `EmailTemplate` |
| `templates.update(template_id, payload, options=None)` | `PATCH /templates/{id}` | `EmailTemplate` |
| `templates.remove(template_id, options=None)` | `DELETE /templates/{id}` | `None` |
| `templates.preview(payload, options=None)` | `POST /templates/preview` | `TemplatePreview` |
| `webhooks.create(payload, options=None)` | `POST /webhook-endpoints` | `WebhookEndpoint` |
| `webhooks.list(options=None)` | `GET /webhook-endpoints` | `CursorPage` |
| `webhooks.update(webhook_id, payload, options=None)` | `PATCH /webhook-endpoints/{id}` | `WebhookEndpoint` |
| `webhooks.remove(webhook_id, options=None)` | `DELETE /webhook-endpoints/{id}` | `None` |
| `webhook_events.retry(event_id, options=None)` | `POST /events/{id}/retry` | `RetryWebhookEventResult` |
| `suppressions.add(payload, options=None)` | `POST /suppressions` | `CreateSuppressionResult` |
| `suppressions.list(options=None)` | `GET /suppressions` | `CursorPage` |
| `suppressions.remove(recipient, options=None)` | `DELETE /suppressions/{recipient}` | `None` |
| `senders.options(options=None)` | `GET /sms/senders/options` | `SenderIdOptions` |
| `senders.list(options=None)` | `GET /sms/senders` | `SendstackList` |
| `senders.create(payload, options=None)` | `POST /sms/senders` | `SenderIdRequestRef` |
| `senders.get(sender_id, options=None)` | `GET /sms/senders/{id}` | `SenderIdRequest` |
| `senders.upload_kyc(sender_id, payload, options=None)` | `POST /sms/senders/{id}/kyc` | `SenderIdRequestRef` |
| `senders.pay(sender_id, payload, options=None)` | `POST /sms/senders/{id}/pay` | `PaySenderIdResult` |
| `senders.authorization_letter(options=None)` | `GET /sms/authorization-letter` | file bytes |
| `billing.credits(options=None, *, channel=None)` | `GET /billing/credits` | `CreditBalance` |
| `billing.products(options=None)` | `GET /billing/products` | `SendstackList` |
| `billing.checkout(payload, options=None)` | `POST /billing/checkout` | `CheckoutResult` |
| `billing.payments(options=None, *, limit=None)` | `GET /billing/payments` | `SendstackList` |
| `billing.payment(payment_id, options=None)` | `GET /billing/payments/{id}` | `Payment` |
| `billing.purchases(options=None)` | `GET /billing/purchases` | `SendstackList` |

`webhook_events` is also available as `webhookEvents`, `whatsapp_senders` as
`whatsappSenders`, `emails.send_batch` / `sms.send_batch` / `whatsapp.send_batch`
as `emails.sendBatch` / `sms.sendBatch` / `whatsapp.sendBatch`,
`whatsapp_senders.set_default` as `whatsapp_senders.setDefault`, and
`senders.upload_kyc` / `senders.authorization_letter` as `senders.uploadKyc` /
`senders.authorizationLetter`, as convenience camelCase aliases.

Methods take a plain `dict` payload and return plain `dict` responses (the
`{"ok": true, "data": ...}` envelope is unwrapped for you). The exported model
types — `EmailMessage`, `Domain`, `WebhookEndpoint`, and friends — are optional
typing aids you can annotate with.

## Emails

```python
client.emails.send(
    {
        "from": "hello@example.com",
        "to": ["a@example.com", "b@example.com"],
        "reply_to": "support@example.com",
        "subject": "Welcome",
        "html": "<p>Hello</p>",
        "text": "Hello",
        "tags": [{"name": "campaign", "value": "welcome"}],
        "metadata": {"account": "acct_123"},
        "track_opens": True,
        "track_clicks": True,
    }
)
```

`to`, `cc`, `bcc`, and `reply_to` accept a single address or a list.

Batch sends accept either a list or `{"emails": [...]}`:

```python
client.emails.send_batch(
    [
        {"from": "hello@example.com", "to": "a@example.com", "subject": "One", "text": "First"},
        {"from": "hello@example.com", "to": "b@example.com", "subject": "Two", "text": "Second"},
    ]
)
```

List, fetch, inspect events, then cancel or requeue:

```python
page = client.emails.list(limit=25, status="queued")
message = client.emails.get("msg_123")
events = client.emails.events("msg_123")
client.emails.cancel("msg_123")
client.emails.requeue("msg_123")
```

### Scheduled email

`scheduled_at` accepts an ISO-8601 string or a `datetime` (serialized to
ISO-8601 with a `Z` suffix):

```python
from datetime import datetime, timezone

client.emails.send(
    {
        "from": "hello@example.com",
        "to": "friend@example.com",
        "subject": "Later",
        "text": "Scheduled.",
        "scheduled_at": datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc),
    }
)
```

## Per-channel defaults

`from` (email), `from` (SMS) and `from` (WhatsApp) are usually constant, so set
them once on the client. Each send fills the default in when the call omits it,
and any per-send value overrides it:

```python
client = Sendstack(
    "mlr_live_…",
    emails={"from": "Noria <hello@example.com>"},
    sms={"from": "NORIA"},
    whatsapp={"from": "+254711000000"},
)

client.emails.send({"to": "customer@example.com", "subject": "Welcome", "html": "<p>Hi</p>"})  # from applied
client.sms.send({"to": "+254700000000", "body": "Your code is 4821"})                          # from applied
```

The channel namespaces are bound, so you can alias them for a terser call-site:

```python
sms = client.sms
sms.send({"to": "+254700000000", "body": "Your code is 4821"})
```

## SMS

With `sms={"from": ...}` set on the client (above), a send only needs `to`
and `body`; pass `from` on the call to override for one message:

```python
# Uses the client default sender.
client.sms.send({"to": "+254700000000", "body": "Your code is 1234"})

# Overrides the default for this one message.
client.sms.send({"to": "+254700000001", "body": "Reminder", "from": "CLINIC"})
```

Batch sends accept either a list or `{"messages": [...]}`, and the default
sender is applied per message:

```python
client.sms.send_batch(
    [
        {"to": "+254700000002", "body": "First"},
        {"to": "+254700000003", "body": "Second", "from": "ALERTS"},
    ]
)
```

`sms.list`, `sms.get`, `sms.events`, `sms.cancel`, and `sms.requeue` mirror the
`emails.*` counterparts. SMS responses include a `segments` count — billing is
one credit per segment. `sms.send` also accepts the camelCase aliases
`providerId`, `templateId`, `templateData`, and `scheduledAt`
(`scheduled_at` accepts a `datetime`, serialized to ISO-8601).

## WhatsApp

WhatsApp is sent over the official Meta Cloud API. A send is exactly one content
mode: a saved `template_id` + `template_data` (business-initiated — the
recommended, cross-channel-consistent way, identical to email and SMS), a
free-form `text`/`media` reply (deliverable only inside the 24-hour
customer-service window), or an inline `template` (the advanced escape hatch for
a Meta-approved template you manage directly in Meta).

```python
# Recommended: render a saved WhatsApp template — same shape as emails.send / sms.send.
# SendStack maps your named data onto the ordered parameters Meta expects.
client.whatsapp.send(
    {
        "to": "+254700000000",
        "template_id": "order_update",
        "template_data": {"name": "A. Doe", "ref": "#1042"},
    }
)

# Free-form reply inside the 24h window (uses the client default sender).
client.whatsapp.send({"to": "+254700000000", "text": "Thanks — your order is on the way."})

# Media reply.
client.whatsapp.send(
    {
        "to": "+254700000000",
        "media": {"type": "image", "link": "https://cdn.example.com/receipt.png", "caption": "Receipt"},
    }
)

# Advanced: reference a Meta-approved template directly (positional params, WhatsApp-only).
client.whatsapp.send(
    {
        "to": "+254700000000",
        "template": {"name": "order_update", "language": "en_US", "variables": ["A. Doe", "#1042"]},
    }
)
```

Batch sends accept either a list or `{"messages": [...]}`. `whatsapp.list`,
`whatsapp.get`, `whatsapp.events`, `whatsapp.cancel`, and `whatsapp.requeue`
mirror the `emails.*`/`sms.*` counterparts, and `whatsapp.send` accepts the same
camelCase aliases (`providerId`, `templateId`, `templateData`, `scheduledAt`).
Only template (business-initiated) messages consume a credit; session replies
inside the 24-hour window are free.

Register and manage the WhatsApp Business numbers you send from with
`whatsapp_senders`. The Cloud API access token is stored encrypted and never
returned on reads:

```python
sender = client.whatsapp_senders.create(
    {
        "phoneNumberId": "109876543210",
        "wabaId": "220011223344",
        "accessToken": "EAAG…",   # stored encrypted, never echoed back
        "displayName": "Acme Support",
        "isDefault": True,
    }
)

client.whatsapp_senders.list()
client.whatsapp_senders.set_default(sender["id"])
client.whatsapp_senders.remove(sender["id"])
```

WhatsApp templates are created through the same `templates.*` methods with
`{"channel": "whatsapp"}`, using `template_name`, `language`, and
`body_variables` (camelCase `templateName` / `bodyVariables` also accepted). Give
`body_variables` named `{{ placeholder }}` values in Meta's parameter order (e.g.
`["{{name}}", "{{ref}}"]`) — those names are what `template_data` fills at send
time, so a WhatsApp template is authored just like an email or SMS one.

## Attachments

```python
attachment = client.attachments.upload(
    {
        "filename": "invoice.pdf",
        "content_base64": invoice_pdf_base64,
        "content_type": "application/pdf",
    }
)

client.emails.send(
    {
        "from": "billing@example.com",
        "to": "customer@example.com",
        "subject": "Invoice",
        "text": "Attached.",
        "attachments": [
            {"filename": "invoice.pdf", "attachment_id": attachment["attachment_id"]},
        ],
    }
)
```

### Reading from files

The API accepts strings (`html`/`text`) and base64 (`attachments`). These
stdlib-only helpers do the read-and-encode step so you don't repeat it:

```python
from sendstack import (
    Sendstack,
    html_from_file,
    text_from_file,
    attachment_from_file,
    attachment_from_bytes,
)

client.emails.send(
    {
        "from": "billing@example.com",
        "to": "customer@example.com",
        "subject": "Your invoice",
        "html": html_from_file("templates/invoice.html"),
        "text": text_from_file("templates/invoice.txt"),
        "attachments": [
            # From a path: filename defaults to the basename, content is base64-encoded.
            attachment_from_file("invoices/2026-06.pdf", content_type="application/pdf"),
            # From in-memory bytes (e.g. a generated PDF): filename is required.
            attachment_from_bytes(generated_pdf, filename="summary.pdf", content_type="application/pdf"),
        ],
    }
)
```

- `html_from_file(path, *, encoding="utf-8")` / `text_from_file(...)` — read a text
  file into a string.
- `attachment_from_file(path, *, filename=None, content_type=None, inline=None, content_id=None)`
  — read a file into a base64 attachment `dict`. `filename` defaults to the basename.
  `path` accepts a `str` or any `os.PathLike`.
- `attachment_from_bytes(data, *, filename, content_type=None, inline=None, content_id=None)`
  — encode in-memory `bytes`; `filename` is required.

## Domains

```python
domain = client.domains.create(
    {
        "domain": "example.com",
        "region": "af-south-1",
        "tls": "enforced",
        "capabilities": {"sending": "enabled"},
    }
)

client.domains.verify(domain["id"])
```

## Templates

Templates are channel-aware: pass `"channel": "email"` (the default) or
`"channel": "sms"`. Email templates use `subject`/`html`/`text`; SMS templates
use `body`. Filter/paginate the list with
`client.templates.list(channel="sms", status="published", limit=25)`.

Templates start as **drafts** and must be published before they can send. Sends
render the published snapshot, so editing a live template never changes in-flight
mail until you publish again. Declared `variables` are typed
(`string`/`number`/`boolean`) and may carry a `fallback_value`; a missing
`required` variable with no fallback fails the send with 422.

```python
template = client.templates.create(
    {
        "name": "Welcome",
        "slug": "welcome",
        "subject": "Welcome, {{firstName}}",
        "html": "<p>Hello {{firstName}}</p>",
        "variables": [{"name": "firstName", "type": "string", "required": True}],
        "publish": True,  # create and publish in one call; omit to keep it a draft
    }
)

client.emails.send(
    {
        "from": "hello@example.com",
        "to": "friend@example.com",
        "template_id": template["id"],
        "template_data": {"firstName": "Amina"},
    }
)

# Edit safely, then publish to go live; or clone into a new draft.
client.templates.update(template["id"], {"html": "<p>Welcome, {{firstName}}!</p>"})
client.templates.publish(template["id"])
copy = client.templates.duplicate(template["id"], {"name": "Welcome v2"})
```

`templates.create(...)` returns a result you can chain `.publish()` on to create
then publish in one expression (an alternative to the `publish: True` flag above).
On `AsyncSendstack`, `await` the chain:

```python
published = client.templates.create(
    {"name": "order-confirmation", "subject": "Order", "html": "<p>Thanks</p>"}
).publish()

# async: published = await client.templates.create({...}).publish()
```

Render any template against sample data with `templates.preview` before
sending — for SMS the preview returns the `segments` count so you can check cost
up front:

```python
otp = client.templates.create(
    {
        "channel": "sms",
        "name": "otp",
        "body": "Your code is {{ code }}",
        "sample_data": {"code": "1234"},
    }
)

preview = client.templates.preview({"template_id": otp["id"], "template_data": {"code": "4821"}})
# {"channel": "sms", "body": "Your code is 4821", "segments": 1, "variables": ["code"], ...}
```

## Webhooks

```python
endpoint = client.webhooks.create(
    {
        "url": "https://example.com/webhooks/sendstack",
        "event_types": ["email.sent", "email.failed"],
    }
)

client.webhook_events.retry("event_123")
client.webhooks.update(endpoint["id"], {"enabled": False})
```

## Suppressions

```python
client.suppressions.add({"recipient": "bad@example.com", "reason": "manual"})

suppressions = client.suppressions.list()
client.suppressions.remove("bad@example.com")
```

## SMS sender IDs

`senders.*` drives the alphanumeric SMS sender-ID provisioning flow: read the fee,
networks, and KYC requirements, file a request, upload the signed authorization
letter and KYC documents, then pay the one-time fee (an M-Pesa STK push).

```python
opts = client.senders.options()  # fee, networks, required KYC docs per entity type

request = client.senders.create(
    {
        "requested_id": "ACME",
        "entity_type": "limited_company",
        "networks": ["safaricom", "airtel"],
    }
)

client.senders.upload_kyc(
    request["id"],
    {
        "documents": [
            {"slug": "cert_of_incorporation", "filename": "cert.pdf", "content_base64": cert_pdf_b64}
        ],
        "auth_letter": {"filename": "auth.pdf", "content_base64": auth_pdf_b64},
    },
)

client.senders.pay(request["id"], {"phone": "+254700000000"})

client.senders.list()
client.senders.get(request["id"])
```

`senders.authorization_letter()` downloads the blank authorization-letter template
(a binary body, returned as-is).

## Billing

`billing.*` covers the credit/wallet catalog, checkout, and payment/purchase history.

```python
email = client.billing.credits()                 # default channel: email
sms = client.billing.credits(channel="sms")      # {"remaining": ..., "unlimited": ..., "active_packs": ...}

products = client.billing.products()
checkout = client.billing.checkout({"product_code": "starter_10k", "phone": "+254700000000"})
# method defaults to "mpesa"; pass "method": "wallet" to settle from the prepaid wallet.

payments = client.billing.payments(limit=20)
payment = client.billing.payment("pay_123")  # polls the provider if a pending payment is stale
purchases = client.billing.purchases()
```

## Field Aliases

Python users write idiomatic snake_case, which is exactly the wire format for
email, SMS, WhatsApp, attachment, template, webhook, and domain fields —
`reply_to`, `track_opens`, `track_clicks`, `provider_id`, `template_id`,
`template_data`, `scheduled_at`, `sample_data`, `content_base64`,
`content_type`, `attachment_id`, `content_id`, `event_types`,
`custom_return_path`, `template_name`, `body_variables`, `phone_number_id`,
`waba_id`, `access_token`, `display_name`, `is_default`, `requested_id`,
`entity_type`, `auth_letter`, `product_code`. No translation needed.

The camelCase aliases (`replyTo`, `trackOpens`,
`trackClicks`, `providerId`, `templateId`, `templateData`,
`scheduledAt`, `sampleData`, `contentBase64`, `attachmentId`, `eventTypes`,
`templateName`, `bodyVariables`, `phoneNumberId`, `wabaId`, `accessToken`,
`displayName`, `isDefault`, `requestedId`, `entityType`, `authLetter`,
`productCode`, …)
are also accepted and converted to the wire field names. Everything else is
passed through unchanged, so the SDK stays forward-compatible with new API
fields.

## Request Options

All methods accept a `RequestOptions`. Mutating methods also honor
`idempotency_key`.

```python
from sendstack import RequestOptions

client.emails.send(
    {
        "from": "hello@example.com",
        "to": "friend@example.com",
        "subject": "Hello",
        "text": "Hello",
    },
    RequestOptions(
        idempotency_key="email-123",
        timeout_seconds=10.0,
        query={"debug": True},
        headers={"x-tenant-id": "tenant_123"},
    ),
)
```

Supported options:

- `headers`: extra headers (merged over constructor headers)
- `query`: per-request query params (merged over constructor query)
- `timeout_seconds`: request timeout, default `30.0`
- `authenticated`: set `False` to strip auth headers for a request
- `auth`: a `BearerAuthStrategy` / `HeadersAuthStrategy`, or `False`
- `retry`: a `RetryOptions`, an attempt count, or `False`
- `middleware`: request/response middleware (runs after constructor middleware)
- `parse_response`: custom response parser
- `transform_response`: custom response transformer
- `unwrap_data`: unwrap `{"ok": true, "data": ...}` envelopes, default `True`
- `client`: a per-request `httpx` client
- `idempotency_key`: sets the `Idempotency-Key` header
- `body`: raw body for `request(...)`

## Retries

Retries are off by default (a single attempt). Enable them per request or on the
client:

```python
from sendstack import RequestOptions, RetryOptions

client.emails.list(
    RequestOptions(retry=RetryOptions(max_attempts=3, delay_seconds=0.5))
)

# Or just an attempt count:
client.emails.list(RequestOptions(retry=3))
```

Default retry behavior:

- retries network exceptions, unless they are already a `SendstackError`
- retries responses only for `408`, `425`, `429`, `500`, `502`, `503`, `504`
- uses a short exponential backoff when no custom `delay_seconds` is given

`RetryOptions` accepts `delay_seconds` and `should_retry` as values or callables
(sync or async).

## Custom `httpx` Clients

Inject your own `httpx.Client` or `httpx.AsyncClient`:

```python
import httpx

from sendstack import Sendstack

client = Sendstack("mlr_live_...", client=httpx.Client(timeout=5.0))
```

If you inject a client, the SDK uses it but does not close it for you.

## Middleware

```python
from sendstack import Sendstack


def add_sdk_header(context, next_call):
    context.headers["x-sdk"] = "sendstack-python"
    return next_call(context)


client = Sendstack("mlr_live_...", middleware=[add_sdk_header])
```

Middleware can mutate headers, rewrite the final URL, or short-circuit a request
by returning a response context without calling `next_call`.

## Lower-Level Request

Every resource method uses `request(...)` internally. Use it directly for new
API routes before the SDK grows a typed wrapper:

```python
from sendstack import RequestOptions

result = client.request("GET", "/emails", RequestOptions(query={"limit": 25, "status": "queued"}))
```

Pass `RequestOptions(unwrap_data=False)` if you need the raw `{"ok", "data"}`
envelope.

## Errors

Failed responses raise `SendstackError`.

```python
from sendstack import SendstackError

try:
    client.emails.send({"from": "hello@example.com", "to": "bad", "subject": "Hi", "text": "Hi"})
except SendstackError as error:
    print(error.status_code, error.code, error.message, error.details)
```

`SendstackError` includes:

- `status_code`
- `code`
- `details`
- `response_body`
- `message`

It understands SendStack envelopes (`{"ok": false, "error": {...}}`) as well as
FastAPI-style `{"detail": "..."}` bodies.

## Exports

Clients and errors:

- `Sendstack`, `AsyncSendstack`
- `SendstackClient`, `AsyncSendstackClient` (aliases)
- `SendstackError`
- `DEFAULT_BASE_URL`

Filesystem helpers:

- `html_from_file`, `text_from_file`
- `attachment_from_file`, `attachment_from_bytes`

Auth, options, and machinery:

- `BearerAuthStrategy`, `HeadersAuthStrategy`, `SendstackAuthStrategy`
- `RequestOptions`, `RetryOptions`
- `SendstackMiddleware`, `ResponseParser`, `ResponseTransformer`
- `SendstackRequestContext`, `SendstackResponseContext`, `SendstackRetryContext`

Model types (optional typing aids):

- `Recipient`, `SendstackTag`
- `SendEmailRequest`, `SendEmailResult`, `SendEmailBatchResult`
- `EmailMessage`, `EmailEvent`, `EmailStatus`
- `SendSmsRequest`, `SendSmsResult`, `SendSmsBatchResult`
- `SmsMessage`, `SmsEvent`, `SmsStatus`
- `SendWhatsAppRequest`, `SendWhatsAppResult`, `SendWhatsAppBatchResult`
- `WhatsAppMessage`, `WhatsAppEvent`, `WhatsAppStatus`
- `WhatsAppTemplateRef`, `WhatsAppTemplateCategory`, `WhatsAppMediaRef`
- `CreateWhatsAppSenderRequest`, `WhatsAppSender`, `WhatsAppSenderRef`
- `UploadAttachmentRequest`, `UploadedAttachment`
- `CreateDomainRequest`, `Domain`, `DomainRegion`, `DomainTlsPolicy`, `DomainCapability`
- `CreateTemplateRequest`, `UpdateTemplateRequest`, `EmailTemplate`
- `TemplateChannel`, `TemplateVariable`, `PreviewTemplateRequest`, `TemplatePreview`
- `EmailDefaults`, `SmsDefaults`, `WhatsAppDefaults`
- `CreateWebhookEndpointRequest`, `UpdateWebhookEndpointRequest`, `WebhookEndpoint`
- `WebhookEventType`, `KnownWebhookEvent`
- `RetryWebhookEventResult`
- `CreateSuppressionRequest`, `CreateSuppressionResult`, `Suppression`, `SuppressionReason`
- `CursorPage`, `SendstackList`
- `CreateSenderIdRequest`, `UploadSenderKycRequest`, `PaySenderIdRequest`, `PaySenderIdResult`
- `SenderIdRequest`, `SenderIdRequestRef`, `SenderIdOptions`, `SenderIdNetwork`, `SenderEntityType`
- `CreditBalance`, `CreditChannel`, `BillingProduct`, `CheckoutRequest`, `CheckoutResult`, `Payment`, `Purchase`

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
uv build
```
