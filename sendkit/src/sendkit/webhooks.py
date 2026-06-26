"""Framework-agnostic webhook helpers for Meta verification and SMS delivery reports."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from .core.errors import ConfigurationError, WebhookVerificationError
from .core.utils import coerce_string, normalize_query_mapping
from .events import DeliveryEvent
from .providers.sms.africastalking import parse_africastalking_delivery_report
from .providers.sms.types import SmsClient

RawBody = str | bytes | bytearray


def resolve_meta_subscription_challenge(
    query_params: Mapping[str, Any], verify_token: str
) -> str | None:
    expected = coerce_string(verify_token)

    if not expected:
        raise ConfigurationError("verify_token is required.")

    normalized = normalize_query_mapping(query_params)

    if normalized.get("hub.mode") != "subscribe":
        return None

    if normalized.get("hub.verify_token") != expected:
        return None

    return normalized.get("hub.challenge")


def verify_meta_signature(
    raw_body: RawBody, signature_header: str | None, app_secret: str
) -> bool:
    secret = coerce_string(app_secret)
    header = coerce_string(signature_header)

    if not secret:
        raise ConfigurationError("app_secret is required for signature verification.")

    if not header or not header.startswith("sha256="):
        return False

    provided = header[len("sha256=") :]
    expected = hmac.new(secret.encode("utf-8"), _to_bytes(raw_body), hashlib.sha256).hexdigest()

    if len(provided) != len(expected):
        return False

    return hmac.compare_digest(provided, expected)


def require_valid_meta_signature(
    raw_body: RawBody, signature_header: str | None, app_secret: str
) -> None:
    if not verify_meta_signature(raw_body, signature_header, app_secret):
        raise WebhookVerificationError("Meta webhook signature verification failed.")


def parse_onfon_delivery_report(
    query_params: Mapping[str, Any], client: SmsClient
) -> DeliveryEvent | None:
    return client.parse_delivery_report(query_params)


def parse_africastalking_sms_delivery_report(
    query_params: Mapping[str, Any], client: SmsClient | None = None
) -> DeliveryEvent | None:
    if client is not None:
        return client.parse_delivery_report(query_params)

    report = parse_africastalking_delivery_report(query_params)

    if report.id is None:
        return None

    return DeliveryEvent(
        channel="sms",
        provider="africastalking",
        provider_message_id=report.id,
        recipient=report.phone_number,
        state=_map_africastalking_state(report.status),
        provider_status=report.status,
        error_code=report.failure_reason,
        metadata={
            "networkCode": report.network_code,
            "retryCount": report.retry_count,
        },
        raw=report.raw,
    )


def _map_africastalking_state(status: str | None) -> Any:
    normalized = (status or "").lower()

    if normalized in ("sent", "submitted"):
        return "submitted"

    if normalized in ("success", "delivered"):
        return "delivered"

    if normalized in ("queued", "failed"):
        return normalized

    return "unknown"


def _to_bytes(value: RawBody) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)
