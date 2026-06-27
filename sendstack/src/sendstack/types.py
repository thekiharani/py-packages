"""Public types for the SendStack SDK.

This module holds two layers:

1. Runtime machinery types - the request/response/retry contexts, auth
   strategies, ``RetryOptions`` and ``RequestOptions`` - that the sync and
   async clients pass around.
2. API model types - ``Literal`` unions and ``TypedDict`` shapes for the
   request/response payloads. They are optional typing aids: every method
   accepts a plain ``dict`` and returns a plain ``dict``, but these give editors
   named shapes and field hints for the API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, NotRequired, TypeAlias, TypedDict

import httpx

# The versioned API base. Override via ``base_url`` for other environments;
# include the /api/v1 segment, since resource paths (e.g. /emails) are sent
# relative to whatever base is configured.
DEFAULT_BASE_URL = "https://sendstack.norialabs.com/api/v1"

# Sentinel distinguishing "no body" from an explicit ``None`` body.
UNSET: Any = object()


# --------------------------------------------------------------------------- #
# Query parameter types
# --------------------------------------------------------------------------- #

QueryScalar: TypeAlias = str | int | float | bool | datetime
QueryItem: TypeAlias = QueryScalar | None
QueryValue: TypeAlias = QueryItem | Sequence[QueryItem]
QueryParams: TypeAlias = Mapping[str, QueryValue]


# --------------------------------------------------------------------------- #
# Request / response / retry contexts
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class SendstackRequestContext:
    method: str
    path: str
    url: str
    headers: httpx.Headers
    body: object = UNSET
    timeout_seconds: float | None = None
    attempt: int = 1


@dataclass(slots=True)
class SendstackResponseContext:
    request: SendstackRequestContext
    response: httpx.Response
    payload: object


@dataclass(slots=True)
class SendstackRetryContext:
    request: SendstackRequestContext
    attempt: int
    response: httpx.Response | None = None
    error: object = None


# --------------------------------------------------------------------------- #
# Callable hooks
# --------------------------------------------------------------------------- #

ResponseParser = Callable[
    [httpx.Response, SendstackRequestContext], object | Awaitable[object]
]
ResponseTransformer = Callable[[SendstackResponseContext], object | Awaitable[object]]
RetryPredicate = Callable[[SendstackRetryContext], bool | Awaitable[bool]]
RetryDelay = Callable[[SendstackRetryContext], float | int | Awaitable[float | int]]
MiddlewareNext = Callable[
    [SendstackRequestContext],
    SendstackResponseContext | Awaitable[SendstackResponseContext],
]
SendstackMiddleware = Callable[
    [SendstackRequestContext, MiddlewareNext],
    SendstackResponseContext | Awaitable[SendstackResponseContext],
]


# --------------------------------------------------------------------------- #
# Auth strategies
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class BearerAuthStrategy:
    """Send ``Authorization: Bearer <token>``.

    ``token`` may be a string or a (sync or async) callable resolved per
    request, which is the idiomatic way to plug in short-lived/rotating tokens.
    """

    token: str | Callable[[SendstackRequestContext], str | Awaitable[str]]
    header_name: str = "authorization"
    prefix: str = "Bearer"


@dataclass(slots=True)
class HeadersAuthStrategy:
    """Send arbitrary auth headers, statically or resolved per request."""

    headers: Mapping[str, str] | Callable[
        [SendstackRequestContext],
        Mapping[str, str] | Awaitable[Mapping[str, str]],
    ]


SendstackAuthStrategy: TypeAlias = BearerAuthStrategy | HeadersAuthStrategy


# --------------------------------------------------------------------------- #
# Retry + per-request options
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class RetryOptions:
    max_attempts: int = 2
    delay_seconds: float | int | RetryDelay | None = None
    should_retry: RetryPredicate | None = None


@dataclass(slots=True)
class RequestOptions:
    headers: Mapping[str, str] | httpx.Headers | None = None
    query: QueryParams | None = None
    timeout_seconds: float | None = None
    authenticated: bool | None = None
    auth: SendstackAuthStrategy | bool | None = None
    retry: RetryOptions | int | bool | None = None
    middleware: Sequence[SendstackMiddleware] | None = None
    parse_response: ResponseParser | None = None
    transform_response: ResponseTransformer | None = None
    unwrap_data: bool | None = None
    client: Any | None = None
    idempotency_key: str | None = None
    body: object = UNSET


# --------------------------------------------------------------------------- #
# API model types
# --------------------------------------------------------------------------- #

EmailStatus = Literal["queued", "sending", "sent", "failed", "canceled"]
SmsStatus = EmailStatus
TemplateChannel = Literal["email", "sms"]
DomainRegion = Literal["af-south-1", "us-east-1", "eu-central-1"]
DomainTlsPolicy = Literal["opportunistic", "enforced"]
DomainCapability = Literal["enabled", "disabled"]
SuppressionReason = Literal["bounce", "complaint", "manual"]
KnownWebhookEvent = Literal[
    "email.queued",
    "email.sending",
    "email.sent",
    "email.failed",
    "email.canceled",
    "email.delivered",
    "email.opened",
    "email.clicked",
    "email.bounced",
    "email.complained",
]
WebhookEventType: TypeAlias = str

# ``to``/``cc``/``bcc``/``reply_to`` accept a single address or a list.
Recipient: TypeAlias = str | Sequence[str]


class SendstackTag(TypedDict):
    name: str
    value: str


class TemplateReference(TypedDict):
    id: str
    variables: NotRequired[Mapping[str, Any]]


# ``from`` is a reserved word, so the email request must use functional syntax.
SendEmailRequest = TypedDict(
    "SendEmailRequest",
    {
        "from": str,
        "to": Recipient,
        "cc": Recipient,
        "bcc": Recipient,
        "reply_to": Recipient,
        "subject": str,
        "html": str,
        "text": str,
        "headers": Mapping[str, str],
        "attachments": Sequence[Mapping[str, Any]],
        "metadata": Mapping[str, str],
        "tags": Sequence[SendstackTag],
        "track_opens": bool,
        "track_clicks": bool,
        "provider_id": str,
        "template_id": str,
        "template_data": Mapping[str, Any],
        "template": TemplateReference,
        "scheduled_at": str | datetime,
    },
    total=False,
)


class SendEmailResult(TypedDict):
    id: str
    status: str


class SendEmailBatchResult(TypedDict):
    batch_id: str
    data: list[SendEmailResult]


EmailMessage = TypedDict(
    "EmailMessage",
    {
        "id": str,
        "status": str,
        "from": str,
        "to": list[str],
        "cc": list[str],
        "bcc": list[str],
        "subject": str,
        "batch_id": str | None,
        "provider_id": str | None,
        "provider_message_id": str | None,
        "attempts": int,
        "scheduled_at": str | None,
        "sent_at": str | None,
        "last_error": str | None,
        "metadata": Mapping[str, Any],
        "tags": list[SendstackTag],
        "created_at": str,
    },
)


class EmailEvent(TypedDict):
    id: str
    message_id: NotRequired[str | None]
    type: str
    occurred_at: NotRequired[str]


class UploadAttachmentRequest(TypedDict):
    filename: str
    content_base64: NotRequired[str]
    content_type: NotRequired[str]


class UploadedAttachment(TypedDict):
    attachment_id: str
    sha256: str
    size_bytes: int
    filename: str
    content_type: str | None


class DomainCapabilities(TypedDict, total=False):
    sending: DomainCapability
    receiving: DomainCapability


class CreateDomainRequest(TypedDict, total=False):
    domain: str
    name: str
    provider_id: str
    region: DomainRegion
    tls: DomainTlsPolicy
    capabilities: DomainCapabilities
    custom_return_path: str


class Domain(TypedDict):
    id: str
    tenantId: str
    domain: str
    status: str
    createdAt: str


class TemplateVariable(TypedDict, total=False):
    name: str
    required: bool
    description: str
    example: str


class CreateTemplateRequest(TypedDict, total=False):
    channel: TemplateChannel
    name: str
    slug: str
    subject: str
    html: str
    text: str
    body: str
    variables: Sequence[TemplateVariable]
    sample_data: Mapping[str, Any]


class UpdateTemplateRequest(TypedDict, total=False):
    subject: str
    html: str | None
    text: str | None
    body: str
    variables: Sequence[TemplateVariable]
    sample_data: Mapping[str, Any]


class PreviewTemplateRequest(TypedDict, total=False):
    template_id: str
    channel: TemplateChannel
    subject: str
    html: str
    text: str
    body: str
    data: Mapping[str, Any]


class TemplatePreview(TypedDict):
    channel: str
    subject: str | None
    html: str | None
    text: str | None
    body: str | None
    segments: int | None
    variables: list[str]


class EmailTemplate(TypedDict):
    id: str
    tenantId: str
    name: str
    subject: str
    htmlBody: str | None
    textBody: str | None
    createdAt: str


class SendSmsRequest(TypedDict, total=False):
    to: str
    body: str
    sender_id: str
    provider_id: str
    metadata: Mapping[str, str]
    template_id: str
    template_data: Mapping[str, Any]
    scheduled_at: str | datetime


class SendSmsResult(TypedDict):
    id: str
    status: str


class SendSmsBatchResult(TypedDict):
    batch_id: str
    data: list[SendSmsResult]


class SmsMessage(TypedDict):
    id: str
    status: str
    to: str
    body: str
    segments: int
    sender_id: str | None
    provider_id: str | None
    provider_message_id: str | None
    attempts: int
    scheduled_at: str | None
    sent_at: str | None
    last_error: str | None
    metadata: Mapping[str, Any]
    created_at: str


class SmsEvent(TypedDict):
    id: str
    type: str
    occurred_at: NotRequired[str]


class CreateWebhookEndpointRequest(TypedDict, total=False):
    url: str
    event_types: Sequence[WebhookEventType]


class UpdateWebhookEndpointRequest(TypedDict, total=False):
    url: str
    event_types: Sequence[WebhookEventType]
    enabled: bool


class WebhookEndpoint(TypedDict):
    id: str
    tenantId: str
    url: str
    secret: str
    eventTypes: list[str]
    enabled: bool
    createdAt: str


class RetryWebhookEventResult(TypedDict):
    id: str
    webhook_status: str


class CreateSuppressionRequest(TypedDict, total=False):
    recipient: str
    reason: SuppressionReason


class CreateSuppressionResult(TypedDict):
    recipient: str
    reason: str


class Suppression(TypedDict):
    id: str
    tenantId: str
    recipient: str
    reason: str
    createdAt: str


class CursorPage(TypedDict):
    data: list[Any]
    next_cursor: NotRequired[str | None]
