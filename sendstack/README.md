# `sendstack`

Official Python SDK for the SendStack email SaaS API.

Built on `httpx`, it ships both a synchronous client (`Sendstack`) and an
asynchronous client (`AsyncSendstack`) covering the SendStack developer API.

Use it for:

- transactional and scheduled email
- batch email
- reusable attachment uploads
- sending domains
- email templates
- webhook endpoints and webhook event retries
- suppression lists

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

The SDK defaults to `https://mailer.norialabs.com`, matching the current live
API. Override it when you move to the SendStack domain:

```python
client = Sendstack(token, base_url="https://sendstack.norialabs.com")
```

## Docs Split

This README is the package guide: install, initialization, SDK methods, request
options, errors, and examples.

The SaaS docs remain the canonical source for product/API behavior: account
setup, API tokens, domain verification, DNS records, webhook event catalogs,
deliverability concepts, provider behavior, dashboard workflows, and the raw
HTTP API reference. Current live SaaS docs are at
`https://mailer.norialabs.com/api/docs`.

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
    base_url="https://mailer.norialabs.com",
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
| `domains.create(payload, options=None)` | `POST /domains` | `Domain` |
| `domains.list(options=None)` | `GET /domains` | `CursorPage` |
| `domains.get(domain_id, options=None)` | `GET /domains/{id}` | `Domain` |
| `domains.verify(domain_id, options=None)` | `POST /domains/{id}/verify` | `Domain` |
| `templates.create(payload, options=None)` | `POST /templates` | `EmailTemplate` |
| `templates.list(options=None)` | `GET /templates` | `CursorPage` |
| `templates.get(template_id, options=None)` | `GET /templates/{id}` | `EmailTemplate` |
| `templates.update(template_id, payload, options=None)` | `PATCH /templates/{id}` | `EmailTemplate` |
| `templates.remove(template_id, options=None)` | `DELETE /templates/{id}` | `None` |
| `webhooks.create(payload, options=None)` | `POST /webhook-endpoints` | `WebhookEndpoint` |
| `webhooks.list(options=None)` | `GET /webhook-endpoints` | `CursorPage` |
| `webhooks.update(webhook_id, payload, options=None)` | `PATCH /webhook-endpoints/{id}` | `WebhookEndpoint` |
| `webhooks.remove(webhook_id, options=None)` | `DELETE /webhook-endpoints/{id}` | `None` |
| `webhook_events.retry(event_id, options=None)` | `POST /events/{id}/retry` | `RetryWebhookEventResult` |
| `suppressions.add(payload, options=None)` | `POST /suppressions` | `CreateSuppressionResult` |
| `suppressions.list(options=None)` | `GET /suppressions` | `CursorPage` |
| `suppressions.remove(recipient, options=None)` | `DELETE /suppressions/{recipient}` | `None` |

`webhook_events` is also available as `webhookEvents`, and `emails.send_batch`
as `emails.sendBatch`, as convenience camelCase aliases.

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

```python
template = client.templates.create(
    {
        "name": "Welcome",
        "slug": "welcome",
        "subject": "Welcome, {{firstName}}",
        "html": "<p>Hello {{firstName}}</p>",
        "text": "Hello {{firstName}}",
    }
)

client.emails.send(
    {
        "from": "hello@example.com",
        "to": "friend@example.com",
        "template": {"id": template["id"], "variables": {"firstName": "Amina"}},
    }
)
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

## Field Aliases

Python users write idiomatic snake_case, which is exactly the wire format for
email, attachment, webhook, and domain fields — `reply_to`, `track_opens`,
`track_clicks`, `provider_id`, `template_id`, `template_data`, `scheduled_at`,
`content_base64`, `content_type`, `attachment_id`, `content_id`, `event_types`,
`custom_return_path`. No translation needed.

The camelCase aliases (`replyTo`, `trackOpens`,
`trackClicks`, `providerId`, `templateId`, `templateData`, `scheduledAt`,
`contentBase64`, `attachmentId`, `eventTypes`, …) are also accepted and
converted to the wire field names. Everything else is passed through unchanged,
so the SDK stays forward-compatible with new API fields.

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

- `Recipient`, `SendstackTag`, `TemplateReference`
- `SendEmailRequest`, `SendEmailResult`, `SendEmailBatchResult`
- `EmailMessage`, `EmailEvent`, `EmailStatus`
- `UploadAttachmentRequest`, `UploadedAttachment`
- `CreateDomainRequest`, `Domain`, `DomainRegion`, `DomainTlsPolicy`, `DomainCapability`
- `CreateTemplateRequest`, `UpdateTemplateRequest`, `EmailTemplate`
- `CreateWebhookEndpointRequest`, `UpdateWebhookEndpointRequest`, `WebhookEndpoint`
- `WebhookEventType`, `KnownWebhookEvent`
- `RetryWebhookEventResult`
- `CreateSuppressionRequest`, `CreateSuppressionResult`, `Suppression`, `SuppressionReason`
- `CursorPage`

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
uv build
```
