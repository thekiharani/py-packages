from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

import pytest

from noriapay import (
    AsyncMpesaClient,
    AsyncSasaPayClient,
    ConfigurationError,
    Hooks,
    MpesaClient,
    RequestOptions,
    RetryPolicy,
    SasaPayClient,
    build_mpesa_stk_password,
    build_mpesa_timestamp,
)
from tests.support import FakeAsyncClient, FakeSyncClient, make_json_response


class StaticTokenProvider:
    def __init__(self, token: str = "external-token") -> None:
        self.token = token

    def get_access_token(self, force_refresh: bool = False) -> str:
        return self.token


class AsyncStaticTokenProvider:
    def __init__(self, token: str = "token") -> None:
        self.token = token

    async def get_access_token(self, force_refresh: bool = False) -> str:
        return self.token


def test_build_mpesa_timestamp_formats_datetime() -> None:
    timestamp = build_mpesa_timestamp(dt.datetime(2025, 1, 2, 3, 4, 5))
    assert timestamp == "20250102030405"


def test_build_mpesa_stk_password_encodes_components() -> None:
    value = build_mpesa_stk_password(
        business_short_code="174379",
        passkey="passkey",
        timestamp="20250102030405",
    )
    assert value == "MTc0Mzc5cGFzc2tleTIwMjUwMTAyMDMwNDA1"


def test_mpesa_client_authenticates_supports_hooks_and_covers_remaining_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ConfigurationError):
        MpesaClient()

    sync_client = FakeSyncClient(
        responses=[
            make_json_response(200, {"access_token": "token-123", "expires_in": 3599}),
            make_json_response(200, {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_123"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "stk query"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "register"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "b2c"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "b2b"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "reversal"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "status"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "balance"}),
            make_json_response(200, {"ResponseCode": "0", "Result": "qr"}),
        ]
    )
    seen_headers: list[str] = []

    def before_request(context: Any) -> None:
        context.headers["x-hooked"] = "yes"
        seen_headers.append(context.headers["authorization"])

    client = MpesaClient(
        consumer_key="consumer-key",
        consumer_secret="consumer-secret",
        environment="sandbox",
        client=sync_client,
        default_headers={"x-client-header": "client"},
        hooks=Hooks(before_request=before_request),
    )

    response = client.stk_push(
        {
            "BusinessShortCode": "174379",
            "Password": "password",
            "Timestamp": "20250102030405",
            "TransactionType": "CustomerPayBillOnline",
            "Amount": 1,
            "PartyA": "254700000000",
            "PartyB": "174379",
            "PhoneNumber": "254700000000",
            "CallBackURL": "https://example.com/callback",
            "AccountReference": "INV-001",
            "TransactionDesc": "Payment",
        }
    )
    assert response["ResponseCode"] == "0"
    assert client.stk_push_query(
        {
            "BusinessShortCode": "174379",
            "Password": "password",
            "Timestamp": "20250102030405",
            "CheckoutRequestID": "ws_CO_123",
        }
    )["Result"] == "stk query"
    assert client.register_c2b_urls(
        {
            "ShortCode": "600000",
            "ResponseType": "Completed",
            "ConfirmationURL": "https://example.com/confirm",
            "ValidationURL": "https://example.com/validate",
        },
        version="v1",
    )["Result"] == "register"
    assert client.b2c_payment(
        {
            "InitiatorName": "apiuser",
            "SecurityCredential": "EncryptedPassword",
            "CommandID": "BusinessPayment",
            "Amount": 10,
            "PartyA": "600000",
            "PartyB": "254700000000",
            "Remarks": "B2C",
            "QueueTimeOutURL": "https://example.com/timeout",
            "ResultURL": "https://example.com/result",
        }
    )["Result"] == "b2c"
    assert client.b2b_payment(
        {
            "Initiator": "apiuser",
            "SecurityCredential": "EncryptedPassword",
            "CommandID": "BusinessPayBill",
            "Amount": 20,
            "PartyA": "600000",
            "PartyB": "600001",
            "Remarks": "B2B",
            "AccountReference": "ACC-1",
            "QueueTimeOutURL": "https://example.com/timeout",
            "ResultURL": "https://example.com/result",
        }
    )["Result"] == "b2b"
    assert client.reversal(
        {
            "Initiator": "apiuser",
            "SecurityCredential": "EncryptedPassword",
            "CommandID": "TransactionReversal",
            "TransactionID": "LKXXXX1234",
            "Amount": 30,
            "ReceiverParty": "600000",
            "RecieverIdentifierType": "11",
            "ResultURL": "https://example.com/result",
            "QueueTimeOutURL": "https://example.com/timeout",
            "Remarks": "Reverse",
        }
    )["Result"] == "reversal"
    assert client.transaction_status(
        {
            "Initiator": "apiuser",
            "SecurityCredential": "EncryptedPassword",
            "CommandID": "TransactionStatusQuery",
            "TransactionID": "LKXXXX1234",
            "PartyA": "600000",
            "IdentifierType": "4",
            "ResultURL": "https://example.com/result",
            "QueueTimeOutURL": "https://example.com/timeout",
            "Remarks": "Status",
        }
    )["Result"] == "status"
    assert client.account_balance(
        {
            "Initiator": "apiuser",
            "SecurityCredential": "EncryptedPassword",
            "CommandID": "AccountBalance",
            "PartyA": "600000",
            "IdentifierType": "4",
            "ResultURL": "https://example.com/result",
            "QueueTimeOutURL": "https://example.com/timeout",
            "Remarks": "Account balance",
        }
    )["Result"] == "balance"
    assert client.generate_qr_code(
        {
            "MerchantName": "Noria",
            "MerchantShortCode": "174379",
            "Amount": 40,
            "QRType": "Dynamic",
        },
        options=RequestOptions(headers={"x-request-header": "request"}),
    )["Result"] == "qr"

    assert sync_client.calls[0]["params"] == {"grant_type": "client_credentials"}
    assert sync_client.calls[1]["headers"]["authorization"] == "Bearer token-123"
    assert sync_client.calls[1]["headers"]["x-client-header"] == "client"
    assert sync_client.calls[1]["headers"]["x-hooked"] == "yes"
    assert sync_client.calls[1]["json"]["Amount"] == "1"
    assert sync_client.calls[4]["json"]["Amount"] == "10"
    assert sync_client.calls[9]["headers"]["x-request-header"] == "request"
    assert sync_client.calls[9]["json"]["Amount"] == "40"
    assert seen_headers[0] == "Bearer token-123"

    owned_client = MpesaClient(token_provider=StaticTokenProvider())
    closed: list[str] = []
    monkeypatch.setattr(owned_client._client, "close", lambda: closed.append("closed"))
    with owned_client as entered:
        assert entered is owned_client
    assert closed == ["closed"]

    with pytest.raises(ConfigurationError):
        MpesaClient(
            token_provider=StaticTokenProvider(),
            client=FakeSyncClient(responses=[]),
            session=FakeSyncClient(responses=[]),
        )


def test_async_mpesa_client_supports_all_methods_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        with pytest.raises(ConfigurationError):
            AsyncMpesaClient()

        async_client = FakeAsyncClient(
            responses=[
                make_json_response(200, {"access_token": "token-123", "expires_in": 3599}),
                make_json_response(200, {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_123"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "stk query"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "register"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "b2c"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "b2b"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "reversal"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "status"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "balance"}),
                make_json_response(200, {"ResponseCode": "0", "Result": "qr"}),
            ]
        )
        client = AsyncMpesaClient(
            consumer_key="consumer-key",
            consumer_secret="consumer-secret",
            client=async_client,
        )

        assert (await client.stk_push(
            {
                "BusinessShortCode": "174379",
                "Password": "password",
                "Timestamp": "20250102030405",
                "TransactionType": "CustomerPayBillOnline",
                "Amount": 1,
                "PartyA": "254700000000",
                "PartyB": "174379",
                "PhoneNumber": "254700000000",
                "CallBackURL": "https://example.com/callback",
                "AccountReference": "INV-001",
                "TransactionDesc": "Payment",
            }
        ))["ResponseCode"] == "0"
        assert (
            await client.stk_push_query(
                {
                    "BusinessShortCode": "174379",
                    "Password": "password",
                    "Timestamp": "20250102030405",
                    "CheckoutRequestID": "ws_CO_123",
                }
            )
        )["Result"] == "stk query"
        assert (
            await client.register_c2b_urls(
                {
                    "ShortCode": "600000",
                    "ResponseType": "Completed",
                    "ConfirmationURL": "https://example.com/confirm",
                    "ValidationURL": "https://example.com/validate",
                }
            )
        )["Result"] == "register"
        assert (
            await client.b2c_payment(
                {
                    "InitiatorName": "apiuser",
                    "SecurityCredential": "EncryptedPassword",
                    "CommandID": "BusinessPayment",
                    "Amount": 10,
                    "PartyA": "600000",
                    "PartyB": "254700000000",
                    "Remarks": "B2C",
                    "QueueTimeOutURL": "https://example.com/timeout",
                    "ResultURL": "https://example.com/result",
                }
            )
        )["Result"] == "b2c"
        assert (
            await client.b2b_payment(
                {
                    "Initiator": "apiuser",
                    "SecurityCredential": "EncryptedPassword",
                    "CommandID": "BusinessPayBill",
                    "Amount": 20,
                    "PartyA": "600000",
                    "PartyB": "600001",
                    "Remarks": "B2B",
                    "AccountReference": "ACC-1",
                    "QueueTimeOutURL": "https://example.com/timeout",
                    "ResultURL": "https://example.com/result",
                }
            )
        )["Result"] == "b2b"
        assert (
            await client.reversal(
                {
                    "Initiator": "apiuser",
                    "SecurityCredential": "EncryptedPassword",
                    "CommandID": "TransactionReversal",
                    "TransactionID": "LKXXXX1234",
                    "Amount": 30,
                    "ReceiverParty": "600000",
                    "RecieverIdentifierType": "11",
                    "ResultURL": "https://example.com/result",
                    "QueueTimeOutURL": "https://example.com/timeout",
                    "Remarks": "Reverse",
                }
            )
        )["Result"] == "reversal"
        assert (
            await client.transaction_status(
                {
                    "Initiator": "apiuser",
                    "SecurityCredential": "EncryptedPassword",
                    "CommandID": "TransactionStatusQuery",
                    "TransactionID": "LKXXXX1234",
                    "PartyA": "600000",
                    "IdentifierType": "4",
                    "ResultURL": "https://example.com/result",
                    "QueueTimeOutURL": "https://example.com/timeout",
                    "Remarks": "Status",
                }
            )
        )["Result"] == "status"
        assert (
            await client.account_balance(
                {
                    "Initiator": "apiuser",
                    "SecurityCredential": "EncryptedPassword",
                    "CommandID": "AccountBalance",
                    "PartyA": "600000",
                    "IdentifierType": "4",
                    "ResultURL": "https://example.com/result",
                    "QueueTimeOutURL": "https://example.com/timeout",
                    "Remarks": "Account balance",
                }
            )
        )["Result"] == "balance"
        assert (
            await client.generate_qr_code(
                {
                    "MerchantName": "Noria",
                    "MerchantShortCode": "174379",
                    "Amount": 40,
                    "QRType": "Dynamic",
                }
            )
        )["Result"] == "qr"
        assert async_client.calls[1]["json"]["Amount"] == "1"
        assert async_client.calls[9]["json"]["Amount"] == "40"

        owned_client = AsyncMpesaClient(token_provider=AsyncStaticTokenProvider())
        closed: list[str] = []

        async def fake_close() -> None:
            closed.append("closed")

        monkeypatch.setattr(owned_client._client, "aclose", fake_close)
        async with owned_client as entered:
            assert entered is owned_client
        assert closed == ["closed"]

    asyncio.run(run())


def test_sasapay_sync_client_flows_retry_and_context(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigurationError):
        SasaPayClient(environment="sandbox")

    with pytest.raises(ConfigurationError):
        SasaPayClient(environment="production")

    sync_client = FakeSyncClient(
        responses=[
            make_json_response(
                200,
                {
                    "status": True,
                    "detail": "SUCCESS",
                    "access_token": "sasapay-token",
                    "expires_in": 3600,
                },
            ),
            make_json_response(
                200, {"status": True, "ResponseCode": "0", "CheckoutRequestID": "checkout-123"}
            ),
            make_json_response(500, {"detail": "temporary failure"}),
            make_json_response(200, {"status": True, "ResponseCode": "0"}),
            make_json_response(200, {"status": True, "detail": "b2c"}),
            make_json_response(200, {"status": True, "detail": "b2b"}),
            make_json_response(200, {"status": True, "detail": "otp"}),
        ]
    )
    client = SasaPayClient(
        client_id="client-id",
        client_secret="client-secret",
        environment="sandbox",
        client=sync_client,
    )

    response = client.request_payment(
        {
            "MerchantCode": "600980",
            "NetworkCode": "63902",
            "Currency": "KES",
            "Amount": 1,
            "PhoneNumber": "254700000080",
            "AccountReference": "12345678",
            "TransactionDesc": "Request Payment",
            "CallBackURL": "https://example.com/callback",
        }
    )
    assert response["ResponseCode"] == "0"
    assert client.request_payment(
        {
            "MerchantCode": "600980",
            "NetworkCode": "63902",
            "Currency": "KES",
            "Amount": "1.00",
            "PhoneNumber": "254700000080",
            "AccountReference": "12345678",
            "TransactionDesc": "Request Payment",
            "CallBackURL": "https://example.com/callback",
        },
        options=RequestOptions(
            retry=RetryPolicy(
                max_attempts=2,
                retry_methods=("POST",),
                retry_on_statuses=(500,),
                base_delay_seconds=0.0,
            )
        ),
    )["ResponseCode"] == "0"
    assert client.b2c_payment(
        {
            "MerchantCode": "600980",
            "Amount": 10,
            "Currency": "KES",
            "MerchantTransactionReference": "ref-1",
            "ReceiverNumber": "254700000080",
            "Channel": "63902",
            "Reason": "Payout",
            "CallBackURL": "https://example.com/callback",
        }
    )["detail"] == "b2c"
    assert client.b2b_payment(
        {
            "MerchantCode": "600980",
            "MerchantTransactionReference": "ref-2",
            "Currency": "KES",
            "Amount": 12,
            "ReceiverMerchantCode": "600981",
            "AccountReference": "ACC-2",
            "ReceiverAccountType": "merchant",
            "NetworkCode": "63902",
            "Reason": "Settlement",
            "CallBackURL": "https://example.com/callback",
        }
    )["detail"] == "b2b"

    class BadTokenProvider:
        def get_access_token(self, force_refresh: bool = False) -> str:
            raise AssertionError("token provider should not be called")

    manual_client = SasaPayClient(token_provider=BadTokenProvider(), client=sync_client)
    assert manual_client.process_payment(
        {
            "MerchantCode": "600980",
            "CheckoutRequestID": "checkout-123",
            "VerificationCode": "123456",
        },
        options=RequestOptions(
            access_token="manual-token",
            headers={"x-request-id": "abc-123"},
        ),
    )["detail"] == "otp"

    assert sync_client.calls[0]["params"] == {"grant_type": "client_credentials"}
    assert sync_client.calls[1]["json"]["Amount"] == "1"
    assert sync_client.calls[4]["json"]["Amount"] == "10"
    assert sync_client.calls[5]["json"]["Amount"] == "12"
    assert sync_client.calls[6]["headers"]["authorization"] == "Bearer manual-token"

    owned_client = SasaPayClient(token_provider=StaticTokenProvider())
    closed: list[str] = []
    monkeypatch.setattr(owned_client._client, "close", lambda: closed.append("closed"))
    with owned_client as entered:
        assert entered is owned_client
    assert closed == ["closed"]

    with pytest.raises(ConfigurationError):
        SasaPayClient(
            token_provider=StaticTokenProvider(),
            client=FakeSyncClient(responses=[]),
            session=FakeSyncClient(responses=[]),
        )


def test_async_sasapay_client_flows_and_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        with pytest.raises(ConfigurationError):
            AsyncSasaPayClient(environment="sandbox")

        with pytest.raises(ConfigurationError):
            AsyncSasaPayClient(environment="production")

        async_client = FakeAsyncClient(
            responses=[
                make_json_response(200, {"access_token": "sasapay-token", "expires_in": 3600}),
                make_json_response(
                    200, {"status": True, "ResponseCode": "0", "CheckoutRequestID": "checkout-123"}
                ),
                make_json_response(200, {"status": True, "detail": "otp"}),
                make_json_response(200, {"status": True, "detail": "b2c"}),
                make_json_response(200, {"status": True, "detail": "b2b"}),
            ]
        )
        client = AsyncSasaPayClient(
            client_id="client-id",
            client_secret="client-secret",
            environment="sandbox",
            client=async_client,
        )

        assert (
            await client.request_payment(
                {
                    "MerchantCode": "600980",
                    "NetworkCode": "63902",
                    "Currency": "KES",
                    "Amount": 1,
                    "PhoneNumber": "254700000080",
                    "AccountReference": "12345678",
                    "TransactionDesc": "Request Payment",
                    "CallBackURL": "https://example.com/callback",
                }
            )
        )["ResponseCode"] == "0"
        assert (
            await client.process_payment(
                {
                    "MerchantCode": "600980",
                    "CheckoutRequestID": "checkout-123",
                    "VerificationCode": "123456",
                }
            )
        )["detail"] == "otp"
        assert (
            await client.b2c_payment(
                {
                    "MerchantCode": "600980",
                    "Amount": 10,
                    "Currency": "KES",
                    "MerchantTransactionReference": "ref-1",
                    "ReceiverNumber": "254700000080",
                    "Channel": "63902",
                    "Reason": "Payout",
                    "CallBackURL": "https://example.com/callback",
                }
            )
        )["detail"] == "b2c"
        assert (
            await client.b2b_payment(
                {
                    "MerchantCode": "600980",
                    "MerchantTransactionReference": "ref-2",
                    "Currency": "KES",
                    "Amount": 12,
                    "ReceiverMerchantCode": "600981",
                    "AccountReference": "ACC-2",
                    "ReceiverAccountType": "merchant",
                    "NetworkCode": "63902",
                    "Reason": "Settlement",
                    "CallBackURL": "https://example.com/callback",
                }
            )
        )["detail"] == "b2b"
        assert async_client.calls[1]["json"]["Amount"] == "1"
        assert async_client.calls[3]["json"]["Amount"] == "10"
        assert async_client.calls[4]["json"]["Amount"] == "12"

        owned_client = AsyncSasaPayClient(token_provider=AsyncStaticTokenProvider())
        closed: list[str] = []

        async def fake_close() -> None:
            closed.append("closed")

        monkeypatch.setattr(owned_client._client, "aclose", fake_close)
        async with owned_client as entered:
            assert entered is owned_client
        assert closed == ["closed"]

    asyncio.run(run())
