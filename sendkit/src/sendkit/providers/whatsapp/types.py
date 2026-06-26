"""Request and result models for the Meta WhatsApp Cloud API client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from ...events import DeliveryEvent

WhatsAppSendStatus = Literal["submitted", "failed"]
WhatsAppComponentType = Literal["header", "body", "button"]
WhatsAppMediaType = Literal["image", "audio", "document", "sticker", "video"]
WhatsAppInteractiveType = Literal["button", "list"]
WhatsAppInteractiveHeaderType = Literal["text", "image", "video", "document"]
WhatsAppFlowActionType = Literal["navigate", "data_exchange"]
WhatsAppInboundMessageType = Literal[
    "text",
    "image",
    "audio",
    "document",
    "sticker",
    "video",
    "location",
    "contacts",
    "button",
    "interactive",
    "reaction",
    "unsupported",
]
WhatsAppInboundReplyType = Literal["button", "button_reply", "list_reply"]
WhatsAppTypingIndicatorType = Literal["text"]


@dataclass(slots=True)
class WhatsAppTextRequest:
    recipient: str
    text: str
    preview_url: bool | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateParameter:
    type: str
    value: str | None = None
    provider_options: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateComponent:
    type: WhatsAppComponentType
    parameters: list[WhatsAppTemplateParameter] | None = None
    sub_type: str | None = None
    index: int | None = None


@dataclass(slots=True)
class WhatsAppTemplateRequest:
    recipient: str
    template_name: str
    language_code: str
    components: list[WhatsAppTemplateComponent] | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateButtonDefinition:
    type: str
    text: str | None = None
    phone_number: str | None = None
    url: str | None = None
    example: list[str] | None = None
    flow_id: str | None = None
    flow_name: str | None = None
    flow_json: str | None = None
    flow_action: str | None = None
    navigate_screen: str | None = None
    otp_type: str | None = None
    zero_tap_terms_accepted: bool | None = None
    supported_apps: list[Mapping[str, Any]] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateComponentDefinition:
    type: str
    format: str | None = None
    text: str | None = None
    buttons: list[WhatsAppTemplateButtonDefinition] | None = None
    example: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateListRequest:
    category: list[str] | None = None
    content: str | None = None
    language: list[str] | None = None
    name: str | None = None
    name_or_content: str | None = None
    quality_score: list[str] | None = None
    since: int | None = None
    status: list[str] | None = None
    until: int | None = None
    fields: list[str] | None = None
    summary_fields: list[str] | None = None
    limit: int | None = None
    before: str | None = None
    after: str | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateCreateRequest:
    name: str
    language: str
    category: str
    components: list[WhatsAppTemplateComponentDefinition] | None = None
    allow_category_change: bool | None = None
    parameter_format: str | None = None
    sub_category: str | None = None
    message_send_ttl_seconds: int | None = None
    library_template_name: str | None = None
    is_primary_device_delivery_only: bool | None = None
    creative_sourcing_spec: Mapping[str, Any] | None = None
    library_template_body_inputs: Mapping[str, Any] | None = None
    library_template_button_inputs: list[Mapping[str, Any]] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateUpdateRequest:
    category: str | None = None
    components: list[WhatsAppTemplateComponentDefinition] | None = None
    parameter_format: str | None = None
    message_send_ttl_seconds: int | None = None
    creative_sourcing_spec: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppTemplateDeleteRequest:
    name: str | None = None
    template_id: str | None = None
    template_ids: list[str] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppManagedTemplate:
    provider: str
    template_id: str
    name: str | None = None
    language: str | None = None
    category: str | None = None
    status: str | None = None
    components: list[WhatsAppTemplateComponentDefinition] = field(default_factory=list)
    parameter_format: str | None = None
    sub_category: str | None = None
    previous_category: str | None = None
    correct_category: str | None = None
    rejected_reason: str | None = None
    quality_score: str | None = None
    cta_url_link_tracking_opted_out: bool | None = None
    library_template_name: str | None = None
    message_send_ttl_seconds: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: object = None


@dataclass(slots=True)
class WhatsAppTemplateListSummary:
    total_count: int | None = None
    message_template_count: int | None = None
    message_template_limit: int | None = None
    are_translations_complete: bool | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppTemplateListResult:
    provider: str
    templates: list[WhatsAppManagedTemplate]
    before: str | None = None
    after: str | None = None
    summary: WhatsAppTemplateListSummary | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppTemplateMutationResult:
    provider: str
    success: bool
    template_id: str | None = None
    name: str | None = None
    category: str | None = None
    status: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppTemplateDeleteResult:
    provider: str
    deleted: bool
    name: str | None = None
    template_id: str | None = None
    template_ids: list[str] = field(default_factory=list)
    raw: object = None


@dataclass(slots=True)
class WhatsAppMediaRequest:
    recipient: str
    media_type: WhatsAppMediaType
    media_id: str | None = None
    link: str | None = None
    caption: str | None = None
    filename: str | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppLocationRequest:
    recipient: str
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppContactName:
    formatted_name: str
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    suffix: str | None = None
    prefix: str | None = None


@dataclass(slots=True)
class WhatsAppContactPhone:
    phone: str
    type: str | None = None
    wa_id: str | None = None


@dataclass(slots=True)
class WhatsAppContactEmail:
    email: str
    type: str | None = None


@dataclass(slots=True)
class WhatsAppContactUrl:
    url: str
    type: str | None = None


@dataclass(slots=True)
class WhatsAppContactAddress:
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    country_code: str | None = None
    type: str | None = None


@dataclass(slots=True)
class WhatsAppContactOrg:
    company: str | None = None
    department: str | None = None
    title: str | None = None


@dataclass(slots=True)
class WhatsAppContact:
    name: WhatsAppContactName
    phones: list[WhatsAppContactPhone] | None = None
    emails: list[WhatsAppContactEmail] | None = None
    urls: list[WhatsAppContactUrl] | None = None
    addresses: list[WhatsAppContactAddress] | None = None
    org: WhatsAppContactOrg | None = None
    birthday: str | None = None


@dataclass(slots=True)
class WhatsAppContactsRequest:
    recipient: str
    contacts: list[WhatsAppContact]
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppReactionRequest:
    recipient: str
    message_id: str
    emoji: str
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppInteractiveHeader:
    type: WhatsAppInteractiveHeaderType
    text: str | None = None
    media_id: str | None = None
    link: str | None = None
    filename: str | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppInteractiveButton:
    identifier: str
    title: str


@dataclass(slots=True)
class WhatsAppInteractiveRow:
    identifier: str
    title: str
    description: str | None = None


@dataclass(slots=True)
class WhatsAppInteractiveSection:
    rows: list[WhatsAppInteractiveRow]
    title: str | None = None


@dataclass(slots=True)
class WhatsAppInteractiveRequest:
    recipient: str
    interactive_type: WhatsAppInteractiveType
    body_text: str
    header: WhatsAppInteractiveHeader | None = None
    footer_text: str | None = None
    buttons: list[WhatsAppInteractiveButton] | None = None
    button_text: str | None = None
    sections: list[WhatsAppInteractiveSection] | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppCatalogMessageRequest:
    recipient: str
    body_text: str | None = None
    header: WhatsAppInteractiveHeader | None = None
    footer_text: str | None = None
    thumbnail_product_retailer_id: str | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppProductItem:
    product_retailer_id: str


@dataclass(slots=True)
class WhatsAppProductMessageRequest:
    recipient: str
    catalog_id: str
    product_retailer_id: str
    body_text: str | None = None
    footer_text: str | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppProductSection:
    title: str
    product_items: list[WhatsAppProductItem]


@dataclass(slots=True)
class WhatsAppProductListRequest:
    recipient: str
    catalog_id: str
    sections: list[WhatsAppProductSection]
    header: WhatsAppInteractiveHeader
    body_text: str | None = None
    footer_text: str | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppFlowMessageRequest:
    recipient: str
    flow_cta: str
    flow_id: str | None = None
    flow_name: str | None = None
    body_text: str | None = None
    header: WhatsAppInteractiveHeader | None = None
    footer_text: str | None = None
    flow_token: str | None = None
    flow_action: WhatsAppFlowActionType | None = None
    flow_action_payload: Mapping[str, Any] | None = None
    flow_message_version: str | None = None
    reply_to_message_id: str | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppReadRequest:
    message_id: str
    typing_indicator_type: WhatsAppTypingIndicatorType | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppStatusResult:
    provider: str
    success: bool
    message_id: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppMediaUploadRequest:
    filename: str
    content: bytes | bytearray | memoryview
    mime_type: str
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class WhatsAppMediaUploadResult:
    provider: str
    media_id: str
    raw: object = None


@dataclass(slots=True)
class WhatsAppMediaInfo:
    provider: str
    media_id: str
    url: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    file_size: int | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppMediaDeleteResult:
    provider: str
    media_id: str
    deleted: bool
    raw: object = None


@dataclass(slots=True)
class WhatsAppSendReceipt:
    provider: str
    recipient: str
    status: WhatsAppSendStatus
    provider_message_id: str | None = None
    provider_status: str | None = None
    conversation_id: str | None = None
    error_code: str | None = None
    error_description: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppSendResult:
    provider: str
    accepted: bool
    messages: list[WhatsAppSendReceipt]
    submitted_count: int
    failed_count: int
    error_code: str | None = None
    error_description: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppInboundMedia:
    media_type: WhatsAppMediaType
    media_id: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None
    filename: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppInboundLocation:
    latitude: float | None = None
    longitude: float | None = None
    name: str | None = None
    address: str | None = None
    url: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppInboundReply:
    reply_type: WhatsAppInboundReplyType
    identifier: str | None = None
    title: str | None = None
    description: str | None = None
    payload: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppInboundReaction:
    emoji: str | None = None
    related_message_id: str | None = None
    raw: object = None


@dataclass(slots=True)
class WhatsAppInboundMessage:
    provider: str
    sender_id: str
    message_id: str
    message_type: WhatsAppInboundMessageType
    timestamp: str | None = None
    profile_name: str | None = None
    context_message_id: str | None = None
    forwarded: bool | None = None
    frequently_forwarded: bool | None = None
    text: str | None = None
    media: WhatsAppInboundMedia | None = None
    location: WhatsAppInboundLocation | None = None
    contacts: list[WhatsAppContact] = field(default_factory=list)
    reply: WhatsAppInboundReply | None = None
    reaction: WhatsAppInboundReaction | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: object = None


@runtime_checkable
class WhatsAppClient(Protocol):
    """Structural type implemented by every WhatsApp provider client."""

    provider_name: str

    def parse_events(self, payload: Mapping[str, Any]) -> list[DeliveryEvent]: ...

    def parse_inbound_messages(
        self, payload: Mapping[str, Any]
    ) -> list[WhatsAppInboundMessage]: ...
