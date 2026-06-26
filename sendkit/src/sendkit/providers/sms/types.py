"""Request and result models shared across SMS providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from ...events import DeliveryEvent

SmsSendStatus = Literal["submitted", "failed"]


@dataclass(slots=True)
class SmsMessage:
    recipient: str
    text: str
    reference: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(slots=True)
class SmsSendRequest:
    messages: list[SmsMessage]
    sender_id: str | None = None
    schedule_at: datetime | str | None = None
    is_unicode: bool | None = None
    is_flash: bool | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class SmsSendReceipt:
    provider: str
    recipient: str
    text: str
    status: SmsSendStatus
    provider_message_id: str | None = None
    reference: str | None = None
    provider_error_code: str | None = None
    provider_error_description: str | None = None
    raw: object = None


@dataclass(slots=True)
class SmsSendResult:
    provider: str
    accepted: bool
    messages: list[SmsSendReceipt]
    submitted_count: int
    failed_count: int
    error_code: str | None = None
    error_description: str | None = None
    raw: object = None


@dataclass(slots=True)
class SmsBalanceEntry:
    label: str | None = None
    credits_raw: str | None = None
    credits: float | None = None
    raw: object = None


@dataclass(slots=True)
class SmsBalance:
    provider: str
    entries: list[SmsBalanceEntry]
    raw: object = None


@dataclass(slots=True)
class SmsGroup:
    group_id: str
    name: str
    contact_count: int | None = None
    raw: object = None


@dataclass(slots=True)
class SmsGroupUpsertRequest:
    name: str
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class SmsTemplate:
    template_id: str
    name: str
    body: str
    approved: bool | None = None
    active: bool | None = None
    created_at: str | None = None
    approved_at: str | None = None
    raw: object = None


@dataclass(slots=True)
class SmsTemplateUpsertRequest:
    name: str
    body: str
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class SmsManagementResult:
    provider: str
    success: bool
    message: str | None = None
    resource_id: str | None = None
    raw: object = None


@dataclass(slots=True)
class AfricasTalkingPremiumSmsRequest:
    recipient: str
    text: str
    keyword: str
    link_id: str
    short_code: str | None = None
    retry_duration_in_hours: int | None = None
    metadata: Mapping[str, Any] | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class AfricasTalkingIncomingMessage:
    provider: str
    provider_message_id: str | None = None
    sender: str | None = None
    recipient: str | None = None
    text: str | None = None
    link_id: str | None = None
    date: str | None = None
    network_code: str | None = None
    raw: object = None


@dataclass(slots=True)
class AfricasTalkingFetchMessagesRequest:
    last_received_id: int | None = None
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class AfricasTalkingFetchMessagesResult:
    provider: str
    messages: list[AfricasTalkingIncomingMessage]
    raw: object = None


@dataclass(slots=True)
class AfricasTalkingSubscriptionRequest:
    phone_number: str
    short_code: str
    keyword: str
    provider_options: Mapping[str, Any] | None = None


@dataclass(slots=True)
class AfricasTalkingSubscriptionResult:
    provider: str
    success: bool
    description: str | None = None
    raw: object = None


@dataclass(slots=True)
class AfricasTalkingDeliveryReport:
    raw: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    phone_number: str | None = None
    status: str | None = None
    failure_reason: str | None = None
    network_code: str | None = None
    retry_count: int | None = None


@runtime_checkable
class SmsClient(Protocol):
    """Structural type implemented by every SMS provider client."""

    provider_name: str

    def parse_delivery_report(self, payload: Mapping[str, Any]) -> DeliveryEvent | None: ...
