from __future__ import annotations

import os

import pytest

from noriapay import MpesaClient, PaystackClient, SasaPayClient

pytestmark = pytest.mark.integration


def _require_live_test_mode() -> None:
    if os.environ.get("RUN_LIVE_SANDBOX_TESTS") != "1":
        pytest.skip("Live sandbox tests are disabled. Set RUN_LIVE_SANDBOX_TESTS=1.")


def test_mpesa_live_sandbox_access_token() -> None:
    _require_live_test_mode()
    if not os.environ.get("MPESA_CONSUMER_KEY") or not os.environ.get("MPESA_CONSUMER_SECRET"):
        pytest.skip("M-PESA sandbox credentials are not configured.")

    client = MpesaClient.from_env()
    assert client.get_access_token()


def test_sasapay_live_sandbox_access_token() -> None:
    _require_live_test_mode()
    if not os.environ.get("SASAPAY_CLIENT_ID") or not os.environ.get("SASAPAY_CLIENT_SECRET"):
        pytest.skip("SasaPay sandbox credentials are not configured.")

    client = SasaPayClient.from_env()
    assert client.get_access_token()


def test_paystack_live_test_key_banks_lookup() -> None:
    _require_live_test_mode()
    if not os.environ.get("PAYSTACK_SECRET_KEY"):
        pytest.skip("Paystack test secret key is not configured.")

    client = PaystackClient.from_env()
    response = client.list_banks({"country": "kenya"})
    assert response["status"] is True
    assert isinstance(response.get("data", []), list)
