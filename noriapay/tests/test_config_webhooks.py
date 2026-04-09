from __future__ import annotations

import asyncio

import pytest

from noriapay import (
    PAYSTACK_WEBHOOK_IPS,
    SASAPAY_BASE_URL,
    AsyncMpesaClient,
    AsyncPaystackClient,
    AsyncSasaPayClient,
    ConfigurationError,
    MpesaClient,
    PaystackClient,
    SasaPayClient,
    WebhookVerificationError,
    compute_paystack_signature,
    require_paystack_signature,
    require_source_ip,
    verify_paystack_signature,
    verify_source_ip,
)
from noriapay.config import (
    get_env_environment,
    get_env_float,
    get_optional_env,
    get_required_env,
    resolve_environ,
)
from tests.support import FakeAsyncClient, FakeSyncClient, make_json_response


def test_config_helpers_handle_optional_required_and_typed_env_values() -> None:
    environ = {
        "PRESENT": " value ",
        "FLOAT_VALUE": "15.5",
        "ENVIRONMENT": "production",
    }

    assert resolve_environ(environ) is environ
    assert get_optional_env("PRESENT", environ=environ) == "value"
    assert get_optional_env("MISSING", environ=environ) is None
    assert get_required_env("PRESENT", environ=environ) == "value"
    assert get_env_float("FLOAT_VALUE", environ=environ) == 15.5
    assert get_env_float("MISSING_FLOAT", environ=environ) is None
    assert get_env_environment("ENVIRONMENT", environ=environ, default="sandbox") == "production"
    assert get_env_environment("MISSING_ENV", environ=environ) == "sandbox"

    with pytest.raises(ConfigurationError):
        get_required_env("MISSING", environ=environ)

    with pytest.raises(ConfigurationError):
        get_env_float("BAD_FLOAT", environ={"BAD_FLOAT": "abc"})

    with pytest.raises(ConfigurationError):
        get_env_environment("BAD_ENV", environ={"BAD_ENV": "staging"})


def test_sync_clients_from_env_read_credentials_and_common_options() -> None:
    mpesa_client = FakeSyncClient(
        responses=[make_json_response(200, {"access_token": "mpesa-token", "expires_in": 3600})]
    )
    mpesa = MpesaClient.from_env(
        environ={
            "MPESA_CONSUMER_KEY": "consumer-key",
            "MPESA_CONSUMER_SECRET": "consumer-secret",
            "MPESA_ENVIRONMENT": "production",
            "MPESA_TIMEOUT_SECONDS": "12.5",
            "MPESA_TOKEN_CACHE_SKEW_SECONDS": "30",
        },
        client=mpesa_client,
    )
    assert mpesa.get_access_token() == "mpesa-token"
    assert mpesa_client.calls[0]["url"] == "https://api.safaricom.co.ke/oauth/v1/generate"
    assert mpesa_client.calls[0]["timeout"] == 12.5

    sasapay_client = FakeSyncClient(
        responses=[make_json_response(200, {"access_token": "sasapay-token", "expires_in": 3600})]
    )
    sasapay = SasaPayClient.from_env(
        environ={
            "SASAPAY_CLIENT_ID": "client-id",
            "SASAPAY_CLIENT_SECRET": "client-secret",
            "SASAPAY_ENVIRONMENT": "production",
            "SASAPAY_BASE_URL": "https://api.example.com/sasapay",
            "SASAPAY_TIMEOUT_SECONDS": "20",
        },
        client=sasapay_client,
    )
    assert sasapay.get_access_token() == "sasapay-token"
    assert sasapay_client.calls[0]["url"] == "https://api.example.com/sasapay/auth/token/"
    assert sasapay_client.calls[0]["timeout"] == 20.0

    paystack_client = FakeSyncClient(
        responses=[make_json_response(200, {"status": True, "message": "Banks", "data": []})]
    )
    paystack = PaystackClient.from_env(
        environ={
            "PAYSTACK_SECRET_KEY": "sk_test_123",
            "PAYSTACK_TIMEOUT_SECONDS": "9",
        },
        client=paystack_client,
    )
    assert paystack.list_banks()["status"] is True
    assert paystack_client.calls[0]["headers"]["authorization"] == "Bearer sk_test_123"
    assert paystack_client.calls[0]["timeout"] == 9.0


def test_async_clients_from_env_read_credentials_and_common_options() -> None:
    async def run() -> None:
        mpesa_client = FakeAsyncClient(
            responses=[make_json_response(200, {"access_token": "mpesa-token", "expires_in": 3600})]
        )
        mpesa = AsyncMpesaClient.from_env(
            environ={
                "MPESA_CONSUMER_KEY": "consumer-key",
                "MPESA_CONSUMER_SECRET": "consumer-secret",
                "MPESA_ENVIRONMENT": "production",
                "MPESA_TIMEOUT_SECONDS": "12.5",
                "MPESA_TOKEN_CACHE_SKEW_SECONDS": "30",
            },
            client=mpesa_client,
        )
        assert await mpesa.get_access_token() == "mpesa-token"
        assert mpesa_client.calls[0]["url"] == "https://api.safaricom.co.ke/oauth/v1/generate"
        assert mpesa_client.calls[0]["timeout"] == 12.5

        sasapay_client = FakeAsyncClient(
            responses=[
                make_json_response(200, {"access_token": "sasapay-token", "expires_in": 3600})
            ]
        )
        sasapay = AsyncSasaPayClient.from_env(
            environ={
                "SASAPAY_CLIENT_ID": "client-id",
                "SASAPAY_CLIENT_SECRET": "client-secret",
                "SASAPAY_ENVIRONMENT": "production",
                "SASAPAY_BASE_URL": "https://api.example.com/sasapay",
                "SASAPAY_TIMEOUT_SECONDS": "20",
            },
            client=sasapay_client,
        )
        assert await sasapay.get_access_token() == "sasapay-token"
        assert sasapay_client.calls[0]["url"] == "https://api.example.com/sasapay/auth/token/"
        assert sasapay_client.calls[0]["timeout"] == 20.0

        paystack_client = FakeAsyncClient(
            responses=[make_json_response(200, {"status": True, "message": "Banks", "data": []})]
        )
        paystack = AsyncPaystackClient.from_env(
            environ={
                "PAYSTACK_SECRET_KEY": "sk_test_123",
                "PAYSTACK_TIMEOUT_SECONDS": "9",
            },
            client=paystack_client,
        )
        assert (await paystack.list_banks())["status"] is True
        assert paystack_client.calls[0]["headers"]["authorization"] == "Bearer sk_test_123"
        assert paystack_client.calls[0]["timeout"] == 9.0

    asyncio.run(run())


def test_sasapay_base_url_constant_is_public_sandbox_default() -> None:
    assert SASAPAY_BASE_URL == "https://sandbox.sasapay.app/api/v1"


def test_webhook_helpers_verify_signatures_and_source_ips() -> None:
    raw_body = '{"event":"charge.success"}'
    secret_key = "sk_test_123"
    signature = compute_paystack_signature(raw_body, secret_key)
    bytes_signature = compute_paystack_signature(raw_body.encode("utf-8"), secret_key)

    assert verify_paystack_signature(raw_body, signature, secret_key)
    assert verify_paystack_signature(raw_body.encode("utf-8"), bytes_signature, secret_key)
    assert not verify_paystack_signature(raw_body, "bad-signature", secret_key)
    assert not verify_paystack_signature(raw_body, None, secret_key)

    require_paystack_signature(raw_body, signature, secret_key)
    with pytest.raises(WebhookVerificationError):
        require_paystack_signature(raw_body, "bad-signature", secret_key)

    assert verify_source_ip(PAYSTACK_WEBHOOK_IPS[0], PAYSTACK_WEBHOOK_IPS)
    assert verify_source_ip(" 52.31.139.75 ", PAYSTACK_WEBHOOK_IPS)
    assert not verify_source_ip(None, PAYSTACK_WEBHOOK_IPS)
    assert not verify_source_ip("   ", PAYSTACK_WEBHOOK_IPS)
    assert not verify_source_ip("127.0.0.1", PAYSTACK_WEBHOOK_IPS)
    assert verify_source_ip(PAYSTACK_WEBHOOK_IPS[2], ["", *PAYSTACK_WEBHOOK_IPS])

    require_source_ip(PAYSTACK_WEBHOOK_IPS[1], PAYSTACK_WEBHOOK_IPS)
    with pytest.raises(WebhookVerificationError):
        require_source_ip("127.0.0.1", PAYSTACK_WEBHOOK_IPS)
