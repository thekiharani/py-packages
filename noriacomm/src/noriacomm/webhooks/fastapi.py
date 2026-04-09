from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..channels.sms.gateways.base import SmsGateway
from ..channels.whatsapp.gateways.base import WhatsAppGateway
from ..channels.whatsapp.models import WhatsAppInboundMessage
from ..events import DeliveryEvent
from .meta import require_valid_meta_signature, resolve_meta_subscription_challenge


def fastapi_resolve_meta_subscription_challenge(
    request: Any,
    verify_token: str,
) -> str | None:
    return resolve_meta_subscription_challenge(dict(request.query_params), verify_token)


async def fastapi_parse_onfon_delivery_report(
    request: Any,
    gateway: SmsGateway,
) -> DeliveryEvent | None:
    return gateway.parse_delivery_report(dict(request.query_params))


async def fastapi_parse_meta_delivery_events(
    request: Any,
    gateway: WhatsAppGateway,
    *,
    require_signature: bool = False,
    app_secret: str | None = None,
) -> tuple[DeliveryEvent, ...]:
    payload_bytes = await request.body()
    if require_signature:
        secret = app_secret or getattr(gateway, "app_secret", None)
        require_valid_meta_signature(
            payload_bytes,
            request.headers.get("x-hub-signature-256"),
            secret,
        )

    payload = json.loads(payload_bytes.decode("utf-8") or "{}")
    if not isinstance(payload, Mapping):
        return ()
    return gateway.parse_events(payload)


async def fastapi_parse_meta_inbound_messages(
    request: Any,
    gateway: WhatsAppGateway,
    *,
    require_signature: bool = False,
    app_secret: str | None = None,
) -> tuple[WhatsAppInboundMessage, ...]:
    payload_bytes = await request.body()
    if require_signature:
        secret = app_secret or getattr(gateway, "app_secret", None)
        require_valid_meta_signature(
            payload_bytes,
            request.headers.get("x-hub-signature-256"),
            secret,
        )

    payload = json.loads(payload_bytes.decode("utf-8") or "{}")
    if not isinstance(payload, Mapping):
        return ()
    return gateway.parse_inbound_messages(payload)
