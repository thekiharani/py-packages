from __future__ import annotations

import hashlib
import hmac
from collections.abc import Collection

from .exceptions import WebhookVerificationError

PAYSTACK_WEBHOOK_IPS: tuple[str, ...] = (
    "52.31.139.75",
    "52.49.173.169",
    "52.214.14.220",
)


def compute_paystack_signature(raw_body: bytes | str, secret_key: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        _to_bytes(raw_body),
        hashlib.sha512,
    ).hexdigest()


def verify_paystack_signature(
    raw_body: bytes | str,
    signature: str | None,
    secret_key: str,
) -> bool:
    if not signature:
        return False

    expected = compute_paystack_signature(raw_body, secret_key)
    return hmac.compare_digest(expected, signature.strip().lower())


def require_paystack_signature(
    raw_body: bytes | str,
    signature: str | None,
    secret_key: str,
) -> None:
    if not verify_paystack_signature(raw_body, signature, secret_key):
        raise WebhookVerificationError("Invalid Paystack webhook signature.")


def verify_source_ip(
    source_ip: str | None,
    allowed_ips: Collection[str],
) -> bool:
    if source_ip is None:
        return False

    normalized_source_ip = source_ip.strip()
    if not normalized_source_ip:
        return False

    normalized_allowed_ips = {ip.strip() for ip in allowed_ips if ip.strip()}
    return normalized_source_ip in normalized_allowed_ips


def require_source_ip(
    source_ip: str | None,
    allowed_ips: Collection[str],
) -> None:
    if not verify_source_ip(source_ip, allowed_ips):
        raise WebhookVerificationError("Webhook request did not originate from an allowed IP.")


def _to_bytes(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")
