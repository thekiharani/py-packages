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
WhatsAppStatus = EmailStatus
TemplateChannel = Literal["email", "sms", "whatsapp"]
WhatsAppTemplateCategory = Literal["marketing", "utility", "authentication"]
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


# ``from`` is a reserved word, so the email defaults must use functional syntax.
EmailDefaults = TypedDict("EmailDefaults", {"from": str}, total=False)


# ``from`` is a reserved word, so the SMS defaults must use functional syntax.
SmsDefaults = TypedDict("SmsDefaults", {"from": str}, total=False)


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
    type: str
    required: bool
    fallback_value: str | float | bool
    description: str
    example: str


# ``from`` is a reserved word, so the create request uses functional syntax.
CreateTemplateRequest = TypedDict(
    "CreateTemplateRequest",
    {
        "channel": TemplateChannel,
        "name": str,
        "slug": str,
        "subject": str,
        "html": str,
        "text": str,
        "body": str,
        "template_name": str,
        "language": str,
        "body_variables": Sequence[str],
        "variables": Sequence[TemplateVariable],
        "sample_data": Mapping[str, Any],
        "from": str,
        "from_name": str,
        "reply_to": str,
        "preheader": str,
        "category": str,
        "description": str,
        "tags": Sequence[str],
        "publish": bool,
    },
    total=False,
)

UpdateTemplateRequest = TypedDict(
    "UpdateTemplateRequest",
    {
        "subject": str,
        "html": str | None,
        "text": str | None,
        "body": str,
        "template_name": str,
        "language": str,
        "body_variables": Sequence[str],
        "variables": Sequence[TemplateVariable],
        "sample_data": Mapping[str, Any],
        "from": str,
        "from_name": str,
        "reply_to": str,
        "preheader": str,
        "category": str,
        "description": str,
        "tags": Sequence[str],
    },
    total=False,
)


class PreviewTemplateRequest(TypedDict, total=False):
    template_id: str
    channel: TemplateChannel
    subject: str
    html: str
    text: str
    body: str
    template_data: Mapping[str, Any]


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


# ``from`` is a reserved word, so the SMS request must use functional syntax.
SendSmsRequest = TypedDict(
    "SendSmsRequest",
    {
        "to": str,
        "body": str,
        "from": str,
        "provider_id": str,
        "metadata": Mapping[str, str],
        "template_id": str,
        "template_data": Mapping[str, Any],
        "scheduled_at": str | datetime,
    },
    total=False,
)


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
    sender: str | None
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


class WhatsAppTemplateRef(TypedDict):
    name: str
    language: str
    variables: NotRequired[Sequence[str]]
    category: NotRequired[WhatsAppTemplateCategory]


class WhatsAppMediaRef(TypedDict):
    type: Literal["image", "document", "video"]
    link: str
    caption: NotRequired[str]
    filename: NotRequired[str]


# ``from`` is a reserved word, so the WhatsApp request must use functional syntax.
# A send is exactly one content mode: an approved ``template`` (business-initiated), a
# free-form ``text``/``media`` reply (deliverable only inside the 24h window), or a
# local ``template_id`` reference.
SendWhatsAppRequest = TypedDict(
    "SendWhatsAppRequest",
    {
        "to": str,
        "from": str,
        "template": WhatsAppTemplateRef,
        "text": str,
        "media": WhatsAppMediaRef,
        "provider_id": str,
        "metadata": Mapping[str, str],
        "template_id": str,
        "template_data": Mapping[str, Any],
        "scheduled_at": str | datetime,
    },
    total=False,
)


class SendWhatsAppResult(TypedDict):
    id: str
    status: str


class SendWhatsAppBatchResult(TypedDict):
    batch_id: str
    data: list[SendWhatsAppResult]


class WhatsAppMessage(TypedDict):
    id: str
    status: str
    to: str
    kind: str
    template_name: str | None
    language: str | None
    text: str | None
    sender: str | None
    sender_id: str | None
    provider_id: str | None
    provider_message_id: str | None
    attempts: int
    scheduled_at: str | None
    sent_at: str | None
    last_error: str | None
    metadata: Mapping[str, Any]
    created_at: str


class WhatsAppEvent(TypedDict):
    id: str
    type: str
    occurred_at: NotRequired[str]


# The encrypted ``access_token`` is stored server-side and never returned on reads.
class CreateWhatsAppSenderRequest(TypedDict, total=False):
    phone_number_id: str
    waba_id: str
    access_token: str
    display_name: str
    identifier: str
    is_default: bool


class WhatsAppSender(TypedDict):
    id: str
    identifier: str
    display_name: str | None
    status: str
    is_default: bool
    phone_number_id: str | None
    waba_id: str | None
    verified_name: str | None
    quality_rating: str | None
    has_own_token: bool
    created_at: str
    updated_at: str


class WhatsAppSenderRef(TypedDict):
    id: str
    object: str


# ``from`` is a reserved word, so the WhatsApp defaults must use functional syntax.
WhatsAppDefaults = TypedDict("WhatsAppDefaults", {"from": str}, total=False)


SenderIdNetwork = Literal["safaricom", "airtel", "telkom"]
SenderEntityType = Literal["limited_company", "sole_proprietor"]


class CreateSenderIdRequest(TypedDict, total=False):
    requested_id: str
    entity_type: SenderEntityType
    networks: Sequence[SenderIdNetwork]


class SenderKycDocument(TypedDict, total=False):
    slug: str
    filename: str
    content_base64: str
    content_type: str


class SenderAuthLetter(TypedDict, total=False):
    filename: str
    content_base64: str
    content_type: str


class UploadSenderKycRequest(TypedDict, total=False):
    documents: Sequence[SenderKycDocument]
    auth_letter: SenderAuthLetter


class PaySenderIdRequest(TypedDict):
    phone: str


class PaySenderIdResult(TypedDict):
    payment_id: str
    status: str
    customer_message: str | None


class SenderIdNetworkState(TypedDict, total=False):
    status: str
    fee_cents: int
    approved_at: str | None
    failure_reason: str | None


class SenderIdRequest(TypedDict):
    id: str
    requested_id: str
    entity_type: str
    status: str
    networks: Mapping[str, SenderIdNetworkState]
    total_cents: int
    total_kes: float | None
    missing_kyc: list[str]
    kyc_documents: list[str]
    has_auth_letter: bool
    submitted_via: str
    sender_id: str | None
    review_notes: str | None
    created_at: str
    updated_at: str


class SenderIdRequestRef(TypedDict):
    id: str
    object: str


class SenderIdOptions(TypedDict):
    fee_cents: int
    fee_kes: float
    total_schedule_cents: list[int]
    total_schedule_kes: list[float]
    networks: list[Mapping[str, str]]
    entity_types: list[Mapping[str, Any]]


CreditChannel = Literal["email", "sms", "whatsapp"]


class CreditBalance(TypedDict):
    remaining: int | None
    unlimited: bool
    active_packs: int


class BillingProduct(TypedDict):
    code: str
    name: str
    description: str | None
    kind: str
    tier: str | None
    currency: str
    price_cents: int
    price_kes: float | None
    billing_period: str
    setup_fee_cents: int | None
    setup_fee_kes: float | None
    email_credits: int | None
    sms_credits: int | None
    validity_days: int | None
    limits: Mapping[str, int | None]
    features: Mapping[str, Any]
    support_level: str


class CheckoutRequest(TypedDict, total=False):
    product_code: str
    phone: str
    method: Literal["mpesa", "wallet"]


class CheckoutResult(TypedDict, total=False):
    payment_id: str | None
    status: str
    purchase_id: str | None
    balance_cents: int | None
    customer_message: str | None


class Payment(TypedDict):
    id: str
    product_id: str | None
    purpose: str
    purchase_id: str | None
    status: str
    method: str
    currency: str
    amount_cents: int
    amount_kes: float | None
    payer_phone: str | None
    provider_txn_code: str | None
    failure_reason: str | None
    paid_at: str | None
    created_at: str


class Purchase(TypedDict):
    id: str
    kind: str
    status: str
    quantity: int
    amount_cents: int
    amount_kes: float | None
    email_credits_granted: int | None
    email_credits_remaining: int | None
    starts_at: str
    expires_at: str | None
    payment_method: str | None
    created_at: str


class SendstackList(TypedDict):
    data: list[Any]


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
