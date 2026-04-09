from __future__ import annotations

import asyncio
from typing import Any

import pytest

from noriapay import AsyncPaystackClient, ConfigurationError, Hooks, PaystackClient, RequestOptions
from tests.support import FakeAsyncClient, FakeSyncClient, make_json_response


def test_paystack_client_requires_secret_key_and_supports_sync_flows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ConfigurationError):
        PaystackClient()

    seen_headers: list[str] = []

    def before_request(context: Any) -> None:
        context.headers["x-hooked"] = "yes"
        seen_headers.append(context.headers["authorization"])

    sync_client = FakeSyncClient(
        responses=[
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Authorization URL created",
                    "data": {
                        "authorization_url": "https://checkout.paystack.com/test",
                        "access_code": "ACCESS_test",
                        "reference": "ref-init",
                    },
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Verification successful",
                    "data": {
                        "id": 123,
                        "status": "success",
                        "reference": "ref-init",
                        "amount": 5000,
                        "currency": "KES",
                    },
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Banks retrieved",
                    "data": [
                        {
                            "name": "Safaricom",
                            "code": "MPESA",
                            "country": "Kenya",
                            "currency": "KES",
                            "type": "mobile_money",
                        }
                    ],
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Account number resolved",
                    "data": {
                        "account_number": "247247",
                        "account_name": "Till Transfer Example",
                    },
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Transfer recipient created successfully",
                    "data": {
                        "recipient_code": "RCP_paystack",
                        "type": "mobile_money_business",
                        "currency": "KES",
                        "details": {
                            "account_number": "247247",
                            "bank_code": "MPTILL",
                        },
                    },
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Transfer has been queued",
                    "data": {
                        "transfer_code": "TRF_queued",
                        "status": "otp",
                        "reference": "ref-transfer",
                        "amount": 5000,
                        "currency": "KES",
                    },
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Transfer has been queued",
                    "data": {
                        "transfer_code": "TRF_queued",
                        "status": "success",
                        "reference": "ref-transfer",
                    },
                },
            ),
            make_json_response(
                200,
                {
                    "status": True,
                    "message": "Transfer retrieved",
                    "data": {
                        "transfer_code": "TRF_queued",
                        "status": "success",
                        "reference": "ref-transfer",
                    },
                },
            ),
        ]
    )

    client = PaystackClient(
        secret_key="sk_test_123",
        client=sync_client,
        default_headers={"x-client-header": "client"},
        hooks=Hooks(before_request=before_request),
    )

    assert client.initialize_transaction(
        {
            "amount": 5000,
            "email": "customer@example.com",
            "currency": "KES",
            "reference": "ref-init",
        }
    )["data"]["reference"] == "ref-init"
    assert client.verify_transaction("ref-init")["data"]["status"] == "success"
    assert (
        client.list_banks({"currency": "KES", "type": "mobile_money"})["data"][0]["code"]
        == "MPESA"
    )
    assert client.resolve_account(
        account_number="247247",
        bank_code="MPTILL",
    )["data"]["account_name"] == "Till Transfer Example"
    assert client.create_transfer_recipient(
        {
            "type": "mobile_money_business",
            "name": "Till Transfer Example",
            "account_number": "247247",
            "bank_code": "MPTILL",
            "currency": "KES",
        }
    )["data"]["recipient_code"] == "RCP_paystack"
    assert client.initiate_transfer(
        {
            "source": "balance",
            "amount": 5000,
            "recipient": "RCP_paystack",
            "reference": "ref-transfer",
            "currency": "KES",
            "account_reference": "ACC-123",
        }
    )["data"]["status"] == "otp"
    assert client.finalize_transfer(
        {
            "transfer_code": "TRF_queued",
            "otp": "123456",
        },
        options=RequestOptions(
            access_token="sk_test_override",
            headers={"x-request-id": "req-123"},
        ),
    )["data"]["status"] == "success"
    assert client.verify_transfer("ref-transfer")["data"]["reference"] == "ref-transfer"

    assert sync_client.calls[0]["headers"]["authorization"] == "Bearer sk_test_123"
    assert sync_client.calls[0]["headers"]["x-client-header"] == "client"
    assert sync_client.calls[0]["headers"]["x-hooked"] == "yes"
    assert sync_client.calls[0]["json"]["email"] == "customer@example.com"
    assert sync_client.calls[1]["method"] == "GET"
    assert sync_client.calls[2]["params"] == {"currency": "KES", "type": "mobile_money"}
    assert sync_client.calls[3]["params"] == {
        "account_number": "247247",
        "bank_code": "MPTILL",
    }
    assert sync_client.calls[6]["headers"]["authorization"] == "Bearer sk_test_override"
    assert sync_client.calls[6]["headers"]["x-request-id"] == "req-123"
    assert seen_headers[0] == "Bearer sk_test_123"

    owned_client = PaystackClient(secret_key="sk_test_owned")
    closed: list[str] = []
    monkeypatch.setattr(owned_client._client, "close", lambda: closed.append("closed"))
    with owned_client as entered:
        assert entered is owned_client
    assert closed == ["closed"]

    with pytest.raises(ConfigurationError):
        PaystackClient(
            secret_key="sk_test_123",
            client=FakeSyncClient(responses=[]),
            session=FakeSyncClient(responses=[]),
        )


def test_async_paystack_client_supports_async_flows_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        with pytest.raises(ConfigurationError):
            AsyncPaystackClient()

        async_client = FakeAsyncClient(
            responses=[
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Authorization URL created",
                        "data": {
                            "authorization_url": "https://checkout.paystack.com/test",
                            "access_code": "ACCESS_test",
                            "reference": "ref-init",
                        },
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Verification successful",
                        "data": {
                            "id": 123,
                            "status": "success",
                            "reference": "ref-init",
                            "amount": 5000,
                            "currency": "KES",
                        },
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Banks retrieved",
                        "data": [
                            {
                                "name": "Safaricom",
                                "code": "MPESA",
                                "country": "Kenya",
                                "currency": "KES",
                                "type": "mobile_money",
                            }
                        ],
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Account number resolved",
                        "data": {
                            "account_number": "247247",
                            "account_name": "Till Transfer Example",
                        },
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Transfer recipient created successfully",
                        "data": {
                            "recipient_code": "RCP_paystack",
                            "type": "mobile_money_business",
                            "currency": "KES",
                        },
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Transfer has been queued",
                        "data": {
                            "transfer_code": "TRF_queued",
                            "status": "otp",
                            "reference": "ref-transfer",
                        },
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Transfer has been queued",
                        "data": {
                            "transfer_code": "TRF_queued",
                            "status": "success",
                            "reference": "ref-transfer",
                        },
                    },
                ),
                make_json_response(
                    200,
                    {
                        "status": True,
                        "message": "Transfer retrieved",
                        "data": {
                            "transfer_code": "TRF_queued",
                            "status": "success",
                            "reference": "ref-transfer",
                        },
                    },
                ),
            ]
        )
        client = AsyncPaystackClient(secret_key="sk_test_123", client=async_client)

        assert (
            await client.initialize_transaction(
                {
                    "amount": 5000,
                    "email": "customer@example.com",
                    "currency": "KES",
                    "reference": "ref-init",
                }
            )
        )["data"]["reference"] == "ref-init"
        assert (await client.verify_transaction("ref-init"))["data"]["status"] == "success"
        assert (
            await client.list_banks({"currency": "KES", "type": "mobile_money"})
        )["data"][0]["code"] == "MPESA"
        assert (
            await client.resolve_account(account_number="247247", bank_code="MPTILL")
        )["data"]["account_name"] == "Till Transfer Example"
        assert (
            await client.create_transfer_recipient(
                {
                    "type": "mobile_money_business",
                    "name": "Till Transfer Example",
                    "account_number": "247247",
                    "bank_code": "MPTILL",
                    "currency": "KES",
                }
            )
        )["data"]["recipient_code"] == "RCP_paystack"
        assert (
            await client.initiate_transfer(
                {
                    "source": "balance",
                    "amount": 5000,
                    "recipient": "RCP_paystack",
                    "reference": "ref-transfer",
                    "currency": "KES",
                }
            )
        )["data"]["status"] == "otp"
        assert (
            await client.finalize_transfer(
                {"transfer_code": "TRF_queued", "otp": "123456"},
                options=RequestOptions(access_token="sk_test_override"),
            )
        )["data"]["status"] == "success"
        assert (await client.verify_transfer("ref-transfer"))["data"]["reference"] == "ref-transfer"
        assert async_client.calls[6]["headers"]["authorization"] == "Bearer sk_test_override"

        owned_client = AsyncPaystackClient(secret_key="sk_test_owned")
        closed: list[str] = []

        async def fake_close() -> None:
            closed.append("closed")

        monkeypatch.setattr(owned_client._client, "aclose", fake_close)
        async with owned_client as entered:
            assert entered is owned_client
        assert closed == ["closed"]

    asyncio.run(run())
