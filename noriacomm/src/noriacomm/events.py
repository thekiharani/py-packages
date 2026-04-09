from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

MessageChannel = Literal["sms", "whatsapp"]
DeliveryState = Literal[
    "accepted",
    "queued",
    "submitted",
    "delivered",
    "read",
    "failed",
    "unknown",
]


@dataclass(slots=True)
class DeliveryEvent:
    channel: MessageChannel
    provider: str
    provider_message_id: str
    state: DeliveryState
    recipient: str | None = None
    provider_status: str | None = None
    error_code: str | None = None
    error_description: str | None = None
    occurred_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: object = None
