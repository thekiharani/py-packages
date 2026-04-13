# `sendstack`

Official Python SDK for Sendstack messaging APIs.

`sendstack` is built on `httpx` and gives you sync and async clients for:

- developer API email, SMS, WhatsApp, and health endpoints
- merchant/control-plane messaging routes, including group email
- custom auth, retries, middleware, and injected `httpx` clients
- raw `request(...)` access for endpoints not yet wrapped by a helper

## Install

```bash
pip install sendstack
```

Python requirement: `>=3.11`

For local development:

```bash
uv sync --extra dev
```

## Shared Setup

The examples below assume:

```python
BASE_URL = "https://sendstack.noria.co.ke/api/v1"
API_KEY = "sk_live_example_secret"
MERCHANT_TOKEN = "control-plane-token"
MERCHANT_ID = "merchant_123"
```

Change `BASE_URL` once if your Sendstack host changes.

## Quick Start

### Developer API

```python
from sendstack import Mailer, RequestOptions

client = Mailer(
    API_KEY,
    base_url=BASE_URL,
)

email_message = client.emails.send(
    {
        "from": "Noria Demo <mail@noria.co.ke>",
        "to": ["hello@example.com"],
        "reply_to": ["support@noria.co.ke", "ops@noria.co.ke"],
        "subject": "Hello from Sendstack",
        "html": "<p>Your <strong>SDK</strong> is working.</p>",
        "text": "Your SDK is working.",
    },
    RequestOptions(idempotency_key="welcome-email-1"),
)

sms_quote = client.sms.quote(
    {
        "from": "SENDSTACK",
        "to": "+254722111222",
        "text": "Hello from SMS",
    }
)

whatsapp_message = client.whatsapp.send(
    {
        "from": "WABA",
        "to": "+254733000333",
        "text": "Hello from WhatsApp",
    }
)

print(email_message["id"], email_message["status"])
print(sms_quote["estimated_units"])
print(whatsapp_message["id"], whatsapp_message["status"])
```

### Merchant API

```python
from sendstack import BearerAuthStrategy, Mailer, RequestOptions

merchant_client = Mailer(
    base_url=BASE_URL,
    auth=BearerAuthStrategy(token=MERCHANT_TOKEN),
)

group_quote = merchant_client.merchant.emails.quote_group(
    MERCHANT_ID,
    {
        "from": "sender@example.com",
        "to": ["a@example.com", "b@example.com"],
        "cc": "finance@example.com",
        "subject": "Monthly update",
        "html": "<p>Hello from the control plane</p>",
        "text": "Hello from the control plane",
    },
)

group_send = merchant_client.merchant.emails.send_group(
    MERCHANT_ID,
    {
        "from": "sender@example.com",
        "to": ["a@example.com", "b@example.com"],
        "reply_to": ["support@example.com", "ops@example.com"],
        "subject": "Monthly update",
        "html": "<p>Queued from the control plane</p>",
        "text": "Queued from the control plane",
    },
    RequestOptions(idempotency_key="merchant-group-send-1"),
)

print(group_quote["estimated_units"])
print(group_send["recipient_count"])
```

### Async

```python
import asyncio

from sendstack import AsyncMailer, RequestOptions


async def main() -> None:
    async with AsyncMailer(
        API_KEY,
        base_url=BASE_URL,
    ) as client:
        email_message = await client.emails.send(
            {
                "from": "Noria Demo <mail@noria.co.ke>",
                "to": ["hello@example.com"],
                "subject": "Hello",
                "html": "<p>World</p>",
                "text": "World",
            },
            RequestOptions(idempotency_key="async-email-1"),
        )
        print(email_message["id"])


asyncio.run(main())
```

## How To Read The Examples

- `client`
  The main Sendstack SDK client you use to call the API.
- `client.emails`
  The email part of the API.
- `client.sms`
  The SMS part of the API.
- `client.whatsapp`
  The WhatsApp part of the API.
- `client.merchant`
  Merchant and control-plane routes on a Sendstack client.
- `quote(...)`
  Ask Sendstack for the estimated units before you send a message.
- `send(...)`
  Queue a message for delivery.
- `get(...)`
  Fetch one message by its ID.
- `list(...)`
  Fetch many messages, usually with filters or pagination.
- `health`
  Endpoints that tell you whether the Sendstack service is up.
- variables like `email_message`, `sms_quote`, and `group_send`
  These are just local Python variable names holding API responses.

## Choose A Client

- `Mailer`
  Sync client backed by `httpx.Client`
- `AsyncMailer`
  Async client backed by `httpx.AsyncClient`

Use `AsyncMailer` when your app already runs async code. Use `Mailer` when you need synchronous calls.

## Auth

### Developer API Auth

When you pass a non-empty `api_key`, `sendstack` sends:

```http
X-API-Key: <api_key>
```

That matches the current Sendstack developer API.

```python
from sendstack import Mailer

client = Mailer(
    API_KEY,
    base_url=BASE_URL,
)
```

### Merchant And Control-Plane Auth

Merchant routes usually need a custom auth strategy instead of an API key.

```python
from sendstack import BearerAuthStrategy, Mailer

merchant_client = Mailer(
    base_url=BASE_URL,
    auth=BearerAuthStrategy(token=MERCHANT_TOKEN),
)
```

You can also use `HeadersAuthStrategy` when the target environment expects custom headers.
If you are not using API-key auth, you can omit `api_key` entirely.

### Per-Request Overrides

All helpers and raw requests accept `RequestOptions`. That lets you override auth, headers, timeout, retry, and the `httpx` client for a single call.

## Developer API

### Emails

Available methods:

- `client.emails.quote(payload, options=None)`
- `client.emails.send(payload, options=None)`
- `client.emails.get(email_id, options=None)`
- `client.emails.list(options=None, *, limit=None, cursor=None, per_page=None, status=None)`

Example:

```python
quote = client.emails.quote(
    {
        "from": "sender@example.com",
        "to": ["recipient@example.com"],
        "subject": "Welcome",
        "html": "<p>Hello from Sendstack</p>",
        "text": "Hello from Sendstack",
    }
)

email_message = client.emails.send(
    {
        "from": "sender@example.com",
        "to": ["recipient@example.com"],
        "reply_to": ["support@example.com", "help@example.com"],
        "subject": "Welcome",
        "html": "<p>Hello from Sendstack</p>",
        "text": "Hello from Sendstack",
    }
)

listing = client.emails.list(limit=10, status="queued")
```

Email content rules:

- provide at least one of `html`, `text`, or `attachments`
- `html` is optional
- `text` is optional
- using both `html` and `text` is usually the best default
- the single-email route still requires exactly one `to` recipient
- `to`, `cc`, `bcc`, and `reply_to` may be passed as a string or a list

### SMS

Available methods:

- `client.sms.quote(payload, options=None)`
- `client.sms.send(payload, options=None)`
- `client.sms.get(message_id, options=None)`
- `client.sms.list(options=None, *, limit=None, cursor=None, per_page=None, status=None)`

Example:

```python
quote = client.sms.quote(
    {
        "from": "SENDSTACK",
        "to": "+254722111222",
        "text": "Hello from SMS",
    }
)

sms_message = client.sms.send(
    {
        "from": "SENDSTACK",
        "to": "+254722111222",
        "text": "Queued SMS",
    }
)
```

### WhatsApp

Available methods:

- `client.whatsapp.quote(payload, options=None)`
- `client.whatsapp.send(payload, options=None)`
- `client.whatsapp.get(message_id, options=None)`
- `client.whatsapp.list(options=None, *, limit=None, cursor=None, per_page=None, status=None)`

Example:

```python
quote = client.whatsapp.quote(
    {
        "from": "WABA",
        "to": "+254733000333",
        "text": "Hello from WhatsApp",
    }
)

whatsapp_message = client.whatsapp.send(
    {
        "from": "WABA",
        "to": "+254733000333",
        "text": "Queued WhatsApp",
    }
)
```

Template send example:

```python
whatsapp_message = client.whatsapp.send(
    {
        "from": "WABA",
        "to": "+254733000333",
        "template_id": "11111111-1111-1111-1111-111111111111",
        "template_variables": {"first_name": "Mercy"},
    }
)
```

WhatsApp rules:

- send plain text with `text`
- send a template message with `template_id`
- use `template_variables` only with template sends
- the SDK accepts `template_variables` and normalizes it to the API field `variables`

### Health

Available methods:

- `client.health.live(options=None)`
- `client.health.check(options=None)`
- `client.health.ready(options=None)`

These helpers target Sendstack's root-scoped `/livez`, `/healthz`, and `/readyz` endpoints even when your `base_url` ends in `/api/v1`.

## Merchant API

### Messages

Available methods:

- `client.merchant.messages.list(merchant_id, options=None, *, limit=None, cursor=None, per_page=None, channel=None, status=None)`
- `client.merchant.messages.get(merchant_id, message_id, options=None)`

Example:

```python
messages = merchant_client.merchant.messages.list(
    MERCHANT_ID,
    limit=20,
    channel="email",
    status="queued",
)
```

### Merchant Email

Available methods:

- `client.merchant.emails.quote(merchant_id, payload, options=None)`
- `client.merchant.emails.send(merchant_id, payload, options=None)`
- `client.merchant.emails.quote_group(merchant_id, payload, options=None)`
- `client.merchant.emails.send_group(merchant_id, payload, options=None)`

Compatibility aliases:

- `client.merchant.emails.quoteGroup(...)`
- `client.merchant.emails.sendGroup(...)`

Group email example:

```python
group_send = merchant_client.merchant.emails.send_group(
    MERCHANT_ID,
    {
        "from": "sender@example.com",
        "to": ["a@example.com", "b@example.com"],
        "cc": "finance@example.com",
        "reply_to": ["support@example.com", "ops@example.com"],
        "subject": "Monthly update",
        "html": "<p>Queued group email</p>",
        "text": "Queued group email",
    },
    RequestOptions(idempotency_key="merchant-group-email-1"),
)
```

Merchant group email rules:

- `to` may be a string or a list
- the backend deduplicates recipients across `to`, `cc`, and `bcc`
- use merchant group email for current Sendstack multi-recipient email sends

### Merchant SMS

Available methods:

- `client.merchant.sms.quote(merchant_id, payload, options=None)`
- `client.merchant.sms.send(merchant_id, payload, options=None)`

### Merchant WhatsApp

Available methods:

- `client.merchant.whatsapp.quote(merchant_id, payload, options=None)`
- `client.merchant.whatsapp.send(merchant_id, payload, options=None)`

## Pagination And Idempotency

List helpers support:

- `cursor`
- `limit`
- `per_page`
  Alias for `limit`

Sendstack list responses are returned unchanged and currently use:

- `items`
- `next_cursor`
- `has_more`
- `limit`

Use `RequestOptions(idempotency_key="...")` on send requests when you want Sendstack idempotency protection.

## Request Options

All helpers and raw requests accept `RequestOptions`.

```python
from sendstack import RequestOptions

message = client.emails.send(
    {
        "from": "sender@example.com",
        "to": "hello@example.com",
        "subject": "Hello",
        "html": "<p>Hello</p>",
        "text": "Hello",
        "scheduled_at": "2026-03-28T09:00:00.000Z",
    },
    RequestOptions(
        headers={"x-tenant-id": "tenant_123"},
        timeout_seconds=10.0,
        idempotency_key="tenant-123-send-1",
    ),
)
```

Supported options:

- `headers`
- `query`
- `timeout_seconds`
- `authenticated`
- `auth`
- `retry`
- `middleware`
- `parse_response`
- `transform_response`
- `unwrap_data`
- `client`
- `idempotency_key`
- `body`

Merge rules:

- request headers merge over constructor headers
- request query params merge over constructor query params
- request middleware runs after constructor middleware
- request-level `client`, `timeout_seconds`, `auth`, `retry`, `parse_response`, and `transform_response` replace constructor values

## Customization

### Custom `httpx` Clients

You can inject your own `httpx.Client` or `httpx.AsyncClient`:

```python
import httpx

from sendstack import Mailer

http_client = httpx.Client(timeout=5.0)

client = Mailer(
    API_KEY,
    base_url=BASE_URL,
    client=http_client,
)
```

If you inject your own client, `sendstack` will use it but will not close it for you.

### Retry

```python
from sendstack import RequestOptions, RetryOptions

result = client.emails.list(
    RequestOptions(
        retry=RetryOptions(
            max_attempts=2,
            delay_seconds=0,
        )
    )
)
```

Default retry behavior:

- retries network exceptions by default unless they are already `MailerError`
- retries responses only for `408`, `425`, `429`, `500`, `502`, `503`, `504`
- uses a short exponential backoff when you enable retries without a custom delay

### Middleware

```python
from sendstack import Mailer


def add_sdk_header(context, next_call):
    context.headers["x-sdk"] = "sendstack"
    return next_call(context)


client = Mailer(
    API_KEY,
    base_url=BASE_URL,
    middleware=[add_sdk_header],
)
```

Middleware can:

- mutate headers
- rewrite the final URL
- short-circuit a request by returning a response without calling `next`

### Raw Requests

Use `request(...)` when you want direct access to an endpoint that does not yet have a helper:

```python
from sendstack import RequestOptions

result = client.request(
    "POST",
    "/reports/export",
    RequestOptions(
        body={"format": "csv"},
        headers={"x-request-id": "req_123"},
    ),
)
```

### Custom Response Parsing

By default:

- successful `{ok: true, data: ...}` responses are unwrapped to `data`
- plain JSON responses are returned unchanged
- non-2xx responses raise `MailerError`

You can customize parsing and transformation:

```python
result = client.request(
    "GET",
    "/metrics",
    RequestOptions(
        parse_response=lambda response, _context: response.headers.get("x-total"),
        transform_response=lambda context: {
            "total": int(context.payload),
            "status": context.response.status_code,
        },
    ),
)
```

Use `RequestOptions(unwrap_data=False)` if you need the raw `{ok, data}` envelope.

## Errors

`sendstack` raises `MailerError` for API-level failures.

It understands both:

- Sendstack-style FastAPI errors such as `{"detail": "..."}`
- older mailer-style error envelopes such as `{ok: false, error: {...}}`

Useful fields on `MailerError`:

- `status_code`
- `code`
- `details`
- `response_body`

Example:

```python
from sendstack import MailerError

try:
    client.emails.send(...)
except MailerError as error:
    print(error.status_code)
    print(error.code)
    print(error.details)
```

## Python-Friendly Field Aliases

The SDK keeps wire payloads API-shaped, but it accepts these Python aliases:

- `reply_to -> replyTo`
- `scheduled_at -> scheduledAt`
- `configuration_set_name -> configurationSetName`
- `tenant_name -> tenantName`
- `endpoint_id -> endpointId`
- `feedback_forwarding_email_address -> feedbackForwardingEmailAddress`
- `feedback_forwarding_email_address_identity_arn -> feedbackForwardingEmailAddressIdentityArn`
- `from_email_address_identity_arn -> fromEmailAddressIdentityArn`
- `list_management_options -> listManagementOptions`
- `contact_list_name -> contactListName`
- `topic_name -> topicName`
- `content_type -> contentType`
- `content_id -> contentId`
- `content_disposition -> disposition`
- `template_variables -> variables`
- `expires_at -> expiresAt`

Everything else is passed through as provided so the SDK stays forward-compatible with new API fields.

## Compatibility Appendix

The SDK also includes helpers for older fully mailer-compatible APIs. These are not part of the current public Sendstack API surface:

- `client.emails.send_batch(payloads, options=None)`
- `client.emails.sendBatch(payloads, options=None)`
- `client.domains`
- `client.api_keys`
- `client.apiKeys`
- `client.webhooks`

Use them only when the target API actually exposes those routes.

## Development

Install development dependencies:

```bash
uv sync --extra dev
```

Run lint:

```bash
uv run ruff check .
```

Run tests:

```bash
uv run pytest
```

Build the package:

```bash
uv build
```
