from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

SmsSendStatus = Literal["submitted", "failed"]


@dataclass(slots=True)
class SmsMessage:
    recipient: str
    text: str
    reference: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SmsSendRequest:
    messages: Sequence[SmsMessage]
    sender_id: str | None = None
    schedule_at: datetime | str | None = None
    is_unicode: bool | None = None
    is_flash: bool | None = None
    provider_options: Mapping[str, Any] = field(default_factory=dict)


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
    error_code: str | None
    error_description: str | None
    messages: tuple[SmsSendReceipt, ...]
    raw: object = None

    @property
    def submitted_count(self) -> int:
        return sum(1 for message in self.messages if message.status == "submitted")

    @property
    def failed_count(self) -> int:
        return sum(1 for message in self.messages if message.status == "failed")


@dataclass(slots=True)
class SmsBalanceEntry:
    label: str | None
    credits_raw: str | None
    credits: Decimal | None
    raw: object = None


@dataclass(slots=True)
class SmsBalance:
    provider: str
    entries: tuple[SmsBalanceEntry, ...]
    raw: object = None


SendSmsRequest = SmsSendRequest
SendReceipt = SmsSendReceipt
SendSmsResult = SmsSendResult


@dataclass(slots=True)
class SmsGroup:
    group_id: str
    name: str
    contact_count: int | None = None
    raw: object = None


@dataclass(slots=True)
class SmsGroupUpsertRequest:
    name: str
    provider_options: Mapping[str, Any] = field(default_factory=dict)


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
    provider_options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SmsManagementResult:
    provider: str
    success: bool
    message: str | None = None
    resource_id: str | None = None
    raw: object = None
