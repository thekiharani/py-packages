from __future__ import annotations

from typing import Any

from ..channels.sms.gateways.base import SmsGateway
from ..channels.whatsapp.gateways.base import WhatsAppGateway
from ..channels.whatsapp.models import WhatsAppInboundMessage
from ..events import DeliveryEvent
from .meta import require_valid_meta_signature, resolve_meta_subscription_challenge


def flask_resolve_meta_subscription_challenge(
    request: Any,
    verify_token: str,
) -> str | None:
    return resolve_meta_subscription_challenge(dict(request.args), verify_token)


def flask_parse_onfon_delivery_report(
    request: Any,
    gateway: SmsGateway,
) -> DeliveryEvent | None:
    return gateway.parse_delivery_report(dict(request.args))


def flask_parse_meta_delivery_events(
    request: Any,
    gateway: WhatsAppGateway,
    *,
    require_signature: bool = False,
    app_secret: str | None = None,
) -> tuple[DeliveryEvent, ...]:
    payload_bytes = request.get_data()
    if require_signature:
        secret = app_secret or getattr(gateway, "app_secret", None)
        require_valid_meta_signature(
            payload_bytes,
            request.headers.get("X-Hub-Signature-256"),
            secret,
        )

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return ()
    return gateway.parse_events(payload)


def flask_parse_meta_inbound_messages(
    request: Any,
    gateway: WhatsAppGateway,
    *,
    require_signature: bool = False,
    app_secret: str | None = None,
) -> tuple[WhatsAppInboundMessage, ...]:
    payload_bytes = request.get_data()
    if require_signature:
        secret = app_secret or getattr(gateway, "app_secret", None)
        require_valid_meta_signature(
            payload_bytes,
            request.headers.get("X-Hub-Signature-256"),
            secret,
        )

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return ()
    return gateway.parse_inbound_messages(payload)
