from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

from ..exceptions import ConfigurationError, WebhookVerificationError
from ..utils import coerce_string, normalize_query_mapping


def resolve_meta_subscription_challenge(
    query_params: Mapping[str, object],
    verify_token: str,
) -> str | None:
    expected = coerce_string(verify_token)
    if expected is None:
        raise ConfigurationError("verify_token is required.")

    normalized = normalize_query_mapping(query_params)
    if normalized.get("hub.mode") != "subscribe":
        return None
    if normalized.get("hub.verify_token") != expected:
        return None
    return normalized.get("hub.challenge")


def verify_meta_signature(
    payload: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    secret = coerce_string(app_secret)
    header = coerce_string(signature_header)
    if secret is None:
        raise ConfigurationError("app_secret is required for signature verification.")
    if header is None or not header.startswith("sha256="):
        return False

    provided = header.removeprefix("sha256=")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def require_valid_meta_signature(
    payload: bytes,
    signature_header: str | None,
    app_secret: str,
) -> None:
    if not verify_meta_signature(payload, signature_header, app_secret):
        raise WebhookVerificationError("Meta webhook signature verification failed.")
