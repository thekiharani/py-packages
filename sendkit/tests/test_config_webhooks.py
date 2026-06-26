from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from support import FakeSyncClient, json_response

from sendkit import (
    AfricasTalkingSmsClient,
    ConfigurationError,
    MetaWhatsAppClient,
    OnfonSmsClient,
    WebhookVerificationError,
    parse_africastalking_sms_delivery_report,
    parse_onfon_delivery_report,
    require_valid_meta_signature,
    resolve_meta_subscription_challenge,
    verify_meta_signature,
)


def _ok(_call):
    return json_response({"ErrorCode": "000", "ErrorDescription": "Success", "Data": []})


def test_from_env_resolves_client_configuration():
    sms = OnfonSmsClient.from_env(
        env={
            "ONFON_ACCESS_KEY": "access-key",
            "ONFON_API_KEY": "api-key",
            "ONFON_CLIENT_ID": "client-id",
            "ONFON_SENDER_ID": "NORIA",
            "ONFON_TIMEOUT_SECONDS": "12",
        },
        client=FakeSyncClient(_ok),
    )
    whatsapp = MetaWhatsAppClient.from_env(
        env={
            "META_WHATSAPP_ACCESS_TOKEN": "token",
            "META_WHATSAPP_PHONE_NUMBER_ID": "123456789",
            "META_WHATSAPP_WHATSAPP_BUSINESS_ACCOUNT_ID": "9988776655",
            "META_WHATSAPP_TIMEOUT_SECONDS": "18",
        },
        client=FakeSyncClient(_ok),
    )
    at = AfricasTalkingSmsClient.from_env(
        env={
            "AFRICAS_TALKING_API_KEY": "api-key",
            "AFRICAS_TALKING_USERNAME": "sandbox",
        },
        client=FakeSyncClient(_ok),
    )

    assert sms.provider_name == "onfon"
    assert whatsapp.provider_name == "meta"
    assert at.provider_name == "africastalking"


def test_from_env_missing_variable_raises():
    with pytest.raises(ConfigurationError):
        OnfonSmsClient.from_env(env={}, client=FakeSyncClient(_ok))


def test_provider_clients_validate_required_configuration():
    with pytest.raises(ConfigurationError):
        OnfonSmsClient(access_key="", api_key="api-key", client_id="client-id")
    with pytest.raises(ConfigurationError):
        MetaWhatsAppClient(access_token="", phone_number_id="123456789")


def test_resolve_meta_subscription_challenge():
    challenge = resolve_meta_subscription_challenge(
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "12345",
        },
        "verify-me",
    )
    assert challenge == "12345"
    assert resolve_meta_subscription_challenge({"hub.mode": "ping"}, "verify-me") is None

    with pytest.raises(ConfigurationError):
        resolve_meta_subscription_challenge({}, "")


def test_meta_signature_verification():
    raw_body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()

    assert verify_meta_signature(raw_body, signature, "app-secret") is True
    assert verify_meta_signature(raw_body, "sha256=bad", "app-secret") is False

    with pytest.raises(ConfigurationError):
        verify_meta_signature(raw_body, signature, "")

    require_valid_meta_signature(raw_body, signature, "app-secret")
    with pytest.raises(WebhookVerificationError):
        require_valid_meta_signature(raw_body, "sha256=bad", "app-secret")


def test_delivery_report_delegation():
    sms = OnfonSmsClient(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=FakeSyncClient(_ok),
    )
    onfon_event = parse_onfon_delivery_report(
        {"MessageId": "msg-1", "MobileNumber": "254700123456", "Status": "Delivered"}, sms
    )
    assert onfon_event is not None
    assert onfon_event.provider_message_id == "msg-1"

    at_event = parse_africastalking_sms_delivery_report(
        {"id": "at-1", "phoneNumber": "+254700123456", "status": "Success"}
    )
    assert at_event is not None
    assert at_event.provider == "africastalking"
    assert at_event.state == "delivered"
