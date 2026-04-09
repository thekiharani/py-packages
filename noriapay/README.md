# `noriapay`

Example-first Python SDK for M-PESA Daraja, SasaPay, and Paystack, built on `httpx` with sync and async clients.

## Install

```bash
pip install noriapay
```

## What It Covers

- M-PESA Daraja: STK push, STK query, C2B URL registration, B2C, B2B, reversal, transaction status, account balance, QR generation
- SasaPay: request payment, OTP completion, B2C, B2B
- Paystack: transaction initialize and verify, bank listing, account resolution, transfer recipient creation, transfer initiation, transfer finalization, transfer verification
- Sync and async clients for every supported provider
- Custom `httpx` clients, retry policy, hooks, env-based configuration, webhook verification helpers

## Quick Setup

### Environment Variables

```bash
# M-PESA
export MPESA_CONSUMER_KEY=your_consumer_key
export MPESA_CONSUMER_SECRET=your_consumer_secret
export MPESA_ENVIRONMENT=sandbox
# optional
export MPESA_BASE_URL=
export MPESA_TIMEOUT_SECONDS=30
export MPESA_TOKEN_CACHE_SKEW_SECONDS=60

# SasaPay
export SASAPAY_CLIENT_ID=your_client_id
export SASAPAY_CLIENT_SECRET=your_client_secret
export SASAPAY_ENVIRONMENT=sandbox
export SASAPAY_BASE_URL=https://sandbox.sasapay.app/api/v1
# optional
export SASAPAY_TIMEOUT_SECONDS=30
export SASAPAY_TOKEN_CACHE_SKEW_SECONDS=60

# Paystack
export PAYSTACK_SECRET_KEY=sk_test_xxx
# optional
export PAYSTACK_BASE_URL=https://api.paystack.co
export PAYSTACK_TIMEOUT_SECONDS=30
```

SasaPay note:

- `SASAPAY_BASE_URL` defaults to the sandbox host
- for live SasaPay, set `SASAPAY_ENVIRONMENT=production` and provide the live `SASAPAY_BASE_URL` issued for your account or environment

### Build Clients From Env

```python
from noriapay import (
    AsyncMpesaClient,
    AsyncPaystackClient,
    AsyncSasaPayClient,
    MpesaClient,
    PaystackClient,
    SasaPayClient,
)

mpesa = MpesaClient.from_env()
sasapay = SasaPayClient.from_env()
paystack = PaystackClient.from_env()


async def build_async_clients() -> tuple[
    AsyncMpesaClient,
    AsyncSasaPayClient,
    AsyncPaystackClient,
]:
    return (
        AsyncMpesaClient.from_env(),
        AsyncSasaPayClient.from_env(),
        AsyncPaystackClient.from_env(),
    )
```

### Direct Construction

```python
from noriapay import MpesaClient, PaystackClient, SasaPayClient

mpesa = MpesaClient(
    consumer_key="consumer-key",
    consumer_secret="consumer-secret",
    environment="sandbox",
)

sasapay = SasaPayClient(
    client_id="client-id",
    client_secret="client-secret",
    environment="sandbox",
)

paystack = PaystackClient(secret_key="sk_test_xxx")
```

## M-PESA Recipes

### Create A Client

```python
from noriapay import MpesaClient

mpesa = MpesaClient.from_env()

# or direct construction
mpesa = MpesaClient(
    consumer_key="consumer-key",
    consumer_secret="consumer-secret",
    environment="sandbox",
)
```

### STK Push

```python
from noriapay import MpesaClient, build_mpesa_stk_password, build_mpesa_timestamp

mpesa = MpesaClient.from_env()

timestamp = build_mpesa_timestamp()
response = mpesa.stk_push(
    {
        "BusinessShortCode": "174379",
        "Password": build_mpesa_stk_password(
            business_short_code="174379",
            passkey="your-passkey",
            timestamp=timestamp,
        ),
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": 1,
        "PartyA": "254700000000",
        "PartyB": "174379",
        "PhoneNumber": "254700000000",
        "CallBackURL": "https://example.com/mpesa/callback",
        "AccountReference": "INV-001",
        "TransactionDesc": "Payment for invoice INV-001",
    }
)

checkout_request_id = response["CheckoutRequestID"]
```

### Query An STK Push

```python
from noriapay import build_mpesa_stk_password, build_mpesa_timestamp

timestamp = build_mpesa_timestamp()
status = mpesa.stk_push_query(
    {
        "BusinessShortCode": "174379",
        "Password": build_mpesa_stk_password(
            business_short_code="174379",
            passkey="your-passkey",
            timestamp=timestamp,
        ),
        "Timestamp": timestamp,
        "CheckoutRequestID": "ws_CO_123456789",
    }
)
```

### Register C2B URLs

```python
response = mpesa.register_c2b_urls(
    {
        "ShortCode": "600000",
        "ResponseType": "Completed",
        "ConfirmationURL": "https://example.com/mpesa/confirmation",
        "ValidationURL": "https://example.com/mpesa/validation",
    },
    version="v2",
)
```

### Send A B2C Payment

```python
response = mpesa.b2c_payment(
    {
        "InitiatorName": "apiuser",
        "SecurityCredential": "EncryptedPassword",
        "CommandID": "BusinessPayment",
        "Amount": 10,
        "PartyA": "600000",
        "PartyB": "254700000000",
        "Remarks": "Customer payout",
        "QueueTimeOutURL": "https://example.com/mpesa/timeout",
        "ResultURL": "https://example.com/mpesa/result",
    }
)
```

### Send A B2B Payment

```python
response = mpesa.b2b_payment(
    {
        "Initiator": "apiuser",
        "SecurityCredential": "EncryptedPassword",
        "CommandID": "BusinessPayBill",
        "Amount": 20,
        "PartyA": "600000",
        "PartyB": "600001",
        "Remarks": "Merchant settlement",
        "AccountReference": "SETTLEMENT-001",
        "QueueTimeOutURL": "https://example.com/mpesa/timeout",
        "ResultURL": "https://example.com/mpesa/result",
    }
)
```

### Reverse A Transaction

```python
response = mpesa.reversal(
    {
        "Initiator": "apiuser",
        "SecurityCredential": "EncryptedPassword",
        "CommandID": "TransactionReversal",
        "TransactionID": "LKXXXX1234",
        "Amount": 30,
        "ReceiverParty": "600000",
        "RecieverIdentifierType": "11",
        "ResultURL": "https://example.com/mpesa/result",
        "QueueTimeOutURL": "https://example.com/mpesa/timeout",
        "Remarks": "Reverse duplicate charge",
    }
)
```

### Check Transaction Status

```python
response = mpesa.transaction_status(
    {
        "Initiator": "apiuser",
        "SecurityCredential": "EncryptedPassword",
        "CommandID": "TransactionStatusQuery",
        "TransactionID": "LKXXXX1234",
        "PartyA": "600000",
        "IdentifierType": "4",
        "ResultURL": "https://example.com/mpesa/result",
        "QueueTimeOutURL": "https://example.com/mpesa/timeout",
        "Remarks": "Status check",
    }
)
```

### Check Account Balance

```python
response = mpesa.account_balance(
    {
        "Initiator": "apiuser",
        "SecurityCredential": "EncryptedPassword",
        "CommandID": "AccountBalance",
        "PartyA": "600000",
        "IdentifierType": "4",
        "ResultURL": "https://example.com/mpesa/result",
        "QueueTimeOutURL": "https://example.com/mpesa/timeout",
        "Remarks": "Balance check",
    }
)
```

### Generate A QR Code

```python
response = mpesa.generate_qr_code(
    {
        "MerchantName": "Noria",
        "MerchantShortCode": "174379",
        "Amount": 40,
        "QRType": "Dynamic",
    }
)
```

### Async M-PESA

```python
from noriapay import AsyncMpesaClient, build_mpesa_stk_password, build_mpesa_timestamp


async def push() -> None:
    async with AsyncMpesaClient.from_env() as mpesa:
        timestamp = build_mpesa_timestamp()
        response = await mpesa.stk_push(
            {
                "BusinessShortCode": "174379",
                "Password": build_mpesa_stk_password(
                    business_short_code="174379",
                    passkey="your-passkey",
                    timestamp=timestamp,
                ),
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": 1,
                "PartyA": "254700000000",
                "PartyB": "174379",
                "PhoneNumber": "254700000000",
                "CallBackURL": "https://example.com/mpesa/callback",
                "AccountReference": "INV-001",
                "TransactionDesc": "Payment",
            }
        )
        print(response["CheckoutRequestID"])
```

### M-PESA Notes

- `MPESA_BASE_URLS["sandbox"]` is `https://sandbox.safaricom.co.ke`
- `MPESA_BASE_URLS["production"]` is `https://api.safaricom.co.ke`
- `build_mpesa_timestamp()` returns `YYYYMMDDHHMMSS`
- `build_mpesa_stk_password()` base64-encodes `shortcode + passkey + timestamp`
- amount fields accept `str`, `int`, or `float`; the SDK serializes them to provider-compatible strings
- you can provide `token_provider=` instead of `consumer_key` and `consumer_secret`

### M-PESA API Map

```python
MpesaClient(
    *,
    consumer_key=None,
    consumer_secret=None,
    token_provider=None,
    environment="sandbox",
    base_url=None,
    client=None,
    session=None,
    timeout_seconds=None,
    token_cache_skew_seconds=60.0,
    default_headers=None,
    retry=None,
    hooks=None,
)

MpesaClient.from_env(
    *,
    prefix="MPESA_",
    environ=None,
    token_provider=None,
    client=None,
    session=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

mpesa.get_access_token(force_refresh=False)
mpesa.stk_push(payload, options=None)
mpesa.stk_push_query(payload, options=None)
mpesa.register_c2b_urls(payload, version="v2", options=None)
mpesa.b2c_payment(payload, options=None)
mpesa.b2b_payment(payload, options=None)
mpesa.reversal(payload, options=None)
mpesa.transaction_status(payload, options=None)
mpesa.account_balance(payload, options=None)
mpesa.generate_qr_code(payload, options=None)
mpesa.close()
```

```python
AsyncMpesaClient(
    *,
    consumer_key=None,
    consumer_secret=None,
    token_provider=None,
    environment="sandbox",
    base_url=None,
    client=None,
    timeout_seconds=None,
    token_cache_skew_seconds=60.0,
    default_headers=None,
    retry=None,
    hooks=None,
)

AsyncMpesaClient.from_env(
    *,
    prefix="MPESA_",
    environ=None,
    token_provider=None,
    client=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

await mpesa.get_access_token(force_refresh=False)
await mpesa.stk_push(payload, options=None)
await mpesa.stk_push_query(payload, options=None)
await mpesa.register_c2b_urls(payload, version="v2", options=None)
await mpesa.b2c_payment(payload, options=None)
await mpesa.b2b_payment(payload, options=None)
await mpesa.reversal(payload, options=None)
await mpesa.transaction_status(payload, options=None)
await mpesa.account_balance(payload, options=None)
await mpesa.generate_qr_code(payload, options=None)
await mpesa.aclose()
```

### M-PESA Exported Models

- `MpesaApiResponse`
- `MpesaStkPushRequest`
- `MpesaStkPushResponse`
- `MpesaStkQueryRequest`
- `MpesaRegisterC2BUrlsRequest`
- `MpesaB2CRequest`
- `MpesaB2BRequest`
- `MpesaReversalRequest`
- `MpesaTransactionStatusRequest`
- `MpesaAccountBalanceRequest`
- `MpesaQrCodeRequest`

## SasaPay Recipes

### Create A Client

```python
from noriapay import SasaPayClient

sasapay = SasaPayClient.from_env()

# or direct construction
sasapay = SasaPayClient(
    client_id="client-id",
    client_secret="client-secret",
    environment="sandbox",
)
```

For production SasaPay:

```python
sasapay = SasaPayClient(
    client_id="client-id",
    client_secret="client-secret",
    environment="production",
    base_url="https://your-live-sasapay-host/api/v1",
)
```

### Request A Mobile Money Payment

```python
response = sasapay.request_payment(
    {
        "MerchantCode": "600980",
        "NetworkCode": "63902",
        "Currency": "KES",
        "Amount": 1,
        "PhoneNumber": "254700000080",
        "AccountReference": "INV-001",
        "TransactionDesc": "Invoice payment",
        "CallBackURL": "https://example.com/sasapay/callback",
    }
)

checkout_request_id = response["CheckoutRequestID"]
```

### Request A Wallet Payment And Complete OTP

`NetworkCode="0"` is the documented SasaPay wallet flow and typically requires `process_payment()`.

```python
request = sasapay.request_payment(
    {
        "MerchantCode": "600980",
        "NetworkCode": "0",
        "Currency": "KES",
        "Amount": "1.00",
        "PhoneNumber": "254700000080",
        "AccountReference": "WALLET-001",
        "TransactionDesc": "Wallet debit",
        "CallBackURL": "https://example.com/sasapay/callback",
    }
)

otp_result = sasapay.process_payment(
    {
        "MerchantCode": "600980",
        "CheckoutRequestID": request["CheckoutRequestID"],
        "VerificationCode": "123456",
    }
)
```

### Send A B2C Payment

```python
response = sasapay.b2c_payment(
    {
        "MerchantCode": "600980",
        "Amount": 10,
        "Currency": "KES",
        "MerchantTransactionReference": "B2C-001",
        "ReceiverNumber": "254700000080",
        "Channel": "63902",
        "Reason": "Customer payout",
        "CallBackURL": "https://example.com/sasapay/callback",
    }
)
```

### Send A B2B Payment

```python
response = sasapay.b2b_payment(
    {
        "MerchantCode": "600980",
        "MerchantTransactionReference": "B2B-001",
        "Currency": "KES",
        "Amount": 12,
        "ReceiverMerchantCode": "600981",
        "AccountReference": "SETTLEMENT-001",
        "ReceiverAccountType": "merchant",
        "NetworkCode": "63902",
        "Reason": "Merchant settlement",
        "CallBackURL": "https://example.com/sasapay/callback",
    }
)
```

### Type Your Callback Handlers

```python
from noriapay import SasaPayC2BCallback, SasaPayC2BIpn, SasaPayTransferCallback


def handle_c2b_callback(payload: SasaPayC2BCallback) -> None:
    print(payload["CheckoutRequestID"], payload["ResultCode"])


def handle_ipn(payload: SasaPayC2BIpn) -> None:
    print(payload["TransID"], payload["TransAmount"])


def handle_transfer_callback(payload: SasaPayTransferCallback) -> None:
    print(payload.get("MerchantTransactionReference"))
```

### Async SasaPay

```python
from noriapay import AsyncSasaPayClient


async def request_payment() -> None:
    async with AsyncSasaPayClient.from_env() as sasapay:
        response = await sasapay.request_payment(
            {
                "MerchantCode": "600980",
                "NetworkCode": "63902",
                "Currency": "KES",
                "Amount": 1,
                "PhoneNumber": "254700000080",
                "AccountReference": "INV-001",
                "TransactionDesc": "Invoice payment",
                "CallBackURL": "https://example.com/sasapay/callback",
            }
        )
        print(response["CheckoutRequestID"])
```

### SasaPay Notes

- `SASAPAY_BASE_URL` is the sandbox default: `https://sandbox.sasapay.app/api/v1`
- `environment="production"` is supported, but you must provide the live `base_url`
- amount fields accept `str`, `int`, or `float`; the SDK serializes them to provider-compatible strings
- you can provide `token_provider=` instead of `client_id` and `client_secret`
- documented network behavior reviewed for this package:
  - `NetworkCode="0"` is SasaPay wallet
  - values such as `63902` represent external payment channels like M-PESA

### SasaPay API Map

```python
SasaPayClient(
    *,
    client_id=None,
    client_secret=None,
    token_provider=None,
    environment="sandbox",
    base_url=None,
    client=None,
    session=None,
    timeout_seconds=None,
    token_cache_skew_seconds=60.0,
    default_headers=None,
    retry=None,
    hooks=None,
)

SasaPayClient.from_env(
    *,
    prefix="SASAPAY_",
    environ=None,
    token_provider=None,
    client=None,
    session=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

sasapay.get_access_token(force_refresh=False)
sasapay.request_payment(payload, options=None)
sasapay.process_payment(payload, options=None)
sasapay.b2c_payment(payload, options=None)
sasapay.b2b_payment(payload, options=None)
sasapay.close()
```

```python
AsyncSasaPayClient(
    *,
    client_id=None,
    client_secret=None,
    token_provider=None,
    environment="sandbox",
    base_url=None,
    client=None,
    timeout_seconds=None,
    token_cache_skew_seconds=60.0,
    default_headers=None,
    retry=None,
    hooks=None,
)

AsyncSasaPayClient.from_env(
    *,
    prefix="SASAPAY_",
    environ=None,
    token_provider=None,
    client=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

await sasapay.get_access_token(force_refresh=False)
await sasapay.request_payment(payload, options=None)
await sasapay.process_payment(payload, options=None)
await sasapay.b2c_payment(payload, options=None)
await sasapay.b2b_payment(payload, options=None)
await sasapay.aclose()
```

### SasaPay Exported Models

- `SasaPayAuthResponse`
- `SasaPayRequestPaymentRequest`
- `SasaPayRequestPaymentResponse`
- `SasaPayProcessPaymentRequest`
- `SasaPayProcessPaymentResponse`
- `SasaPayB2CRequest`
- `SasaPayB2CResponse`
- `SasaPayB2BRequest`
- `SasaPayB2BResponse`
- `SasaPayC2BCallback`
- `SasaPayC2BIpn`
- `SasaPayTransferCallback`

## Paystack Recipes

### Create A Client

```python
from noriapay import PaystackClient

paystack = PaystackClient.from_env()

# or direct construction
paystack = PaystackClient(secret_key="sk_test_xxx")
```

### Initialize A Checkout Transaction

```python
response = paystack.initialize_transaction(
    {
        "email": "customer@example.com",
        "amount": 5000,
        "currency": "KES",
        "reference": "order-123",
        "callback_url": "https://example.com/paystack/callback",
        "metadata": {"order_id": "order-123"},
    }
)

authorization_url = response["data"]["authorization_url"]
reference = response["data"]["reference"]
```

Paystack amounts are lowest-unit integers. `5000` means `50.00` in a 2-decimal currency such as KES.

### Verify A Transaction

```python
verification = paystack.verify_transaction("order-123")

if verification["data"]["status"] == "success":
    print("Payment confirmed")
```

### List Supported Banks

```python
banks = paystack.list_banks(
    {
        "country": "kenya",
        "currency": "KES",
        "type": "mobile_money",
    }
)
```

### Resolve An Account

```python
account = paystack.resolve_account(
    account_number="247247",
    bank_code="MPTILL",
)

print(account["data"]["account_name"])
```

### Create A Transfer Recipient

```python
recipient = paystack.create_transfer_recipient(
    {
        "type": "mobile_money_business",
        "name": "Till Transfer Example",
        "account_number": "247247",
        "bank_code": "MPTILL",
        "currency": "KES",
        "description": "Settlement till",
    }
)

recipient_code = recipient["data"]["recipient_code"]
```

### Initiate A Transfer

```python
transfer = paystack.initiate_transfer(
    {
        "source": "balance",
        "amount": 5000,
        "recipient": recipient_code,
        "reference": "transfer-123",
        "currency": "KES",
        "reason": "Merchant settlement",
        "account_reference": "ACC-123",
    }
)
```

### Finalize A Transfer

```python
result = paystack.finalize_transfer(
    {
        "transfer_code": "TRF_queued",
        "otp": "123456",
    }
)
```

### Verify A Transfer

```python
verification = paystack.verify_transfer("transfer-123")
```

### Async Paystack

```python
from noriapay import AsyncPaystackClient


async def initialize_checkout() -> None:
    async with AsyncPaystackClient.from_env() as paystack:
        response = await paystack.initialize_transaction(
            {
                "email": "customer@example.com",
                "amount": 5000,
                "reference": "order-123",
                "currency": "KES",
            }
        )
        print(response["data"]["authorization_url"])
```

### Verify Paystack Webhooks

```python
from noriapay import PAYSTACK_WEBHOOK_IPS, require_paystack_signature, require_source_ip


def verify_paystack_webhook(raw_body: bytes, signature: str | None, source_ip: str | None) -> None:
    require_paystack_signature(raw_body, signature, "sk_test_xxx")
    require_source_ip(source_ip, PAYSTACK_WEBHOOK_IPS)
```

### Paystack Notes

- `PAYSTACK_BASE_URL` is `https://api.paystack.co`
- environment selection comes from the secret key you use
- `RequestOptions.access_token` can override the bearer token on a single request
- `PaystackClient` and `AsyncPaystackClient` do not use OAuth token lookup
- this package currently covers the initial transaction and transfer subset described here

### Paystack API Map

```python
PaystackClient(
    *,
    secret_key=None,
    base_url=None,
    client=None,
    session=None,
    timeout_seconds=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

PaystackClient.from_env(
    *,
    prefix="PAYSTACK_",
    environ=None,
    client=None,
    session=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

paystack.initialize_transaction(payload, options=None)
paystack.verify_transaction(reference, options=None)
paystack.list_banks(query=None, options=None)
paystack.resolve_account(account_number, bank_code, options=None)
paystack.create_transfer_recipient(payload, options=None)
paystack.initiate_transfer(payload, options=None)
paystack.finalize_transfer(payload, options=None)
paystack.verify_transfer(reference, options=None)
paystack.close()
```

```python
AsyncPaystackClient(
    *,
    secret_key=None,
    base_url=None,
    client=None,
    timeout_seconds=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

AsyncPaystackClient.from_env(
    *,
    prefix="PAYSTACK_",
    environ=None,
    client=None,
    default_headers=None,
    retry=None,
    hooks=None,
)

await paystack.initialize_transaction(payload, options=None)
await paystack.verify_transaction(reference, options=None)
await paystack.list_banks(query=None, options=None)
await paystack.resolve_account(account_number, bank_code, options=None)
await paystack.create_transfer_recipient(payload, options=None)
await paystack.initiate_transfer(payload, options=None)
await paystack.finalize_transfer(payload, options=None)
await paystack.verify_transfer(reference, options=None)
await paystack.aclose()
```

### Paystack Exported Models

- `PaystackApiResponse`
- `PaystackInitializeTransactionRequest`
- `PaystackInitializeTransactionData`
- `PaystackInitializeTransactionResponse`
- `PaystackTransaction`
- `PaystackVerifyTransactionResponse`
- `PaystackBank`
- `PaystackListBanksQuery`
- `PaystackListBanksResponse`
- `PaystackResolveAccountData`
- `PaystackResolveAccountResponse`
- `PaystackTransferRecipientDetails`
- `PaystackTransferRecipient`
- `PaystackCreateTransferRecipientRequest`
- `PaystackCreateTransferRecipientResponse`
- `PaystackTransfer`
- `PaystackInitiateTransferRequest`
- `PaystackInitiateTransferResponse`
- `PaystackFinalizeTransferRequest`
- `PaystackFinalizeTransferResponse`
- `PaystackVerifyTransferResponse`

Returned Paystack payloads also include nested objects such as authorization, customer, recipient details, and cursor metadata. Those nested shapes are part of the provider JSON returned by the SDK even when they are not exported as top-level public names.

## Customization Recipes

### Per-Request Overrides With `RequestOptions`

```python
from noriapay import RequestOptions

result = mpesa.generate_qr_code(
    {
        "MerchantName": "Noria",
        "MerchantShortCode": "174379",
        "Amount": 40,
        "QRType": "Dynamic",
    },
    options=RequestOptions(
        headers={"x-request-id": "req-123"},
        timeout_seconds=10,
    ),
)
```

For Paystack, `access_token` overrides the bearer token for one request:

```python
result = paystack.finalize_transfer(
    {
        "transfer_code": "TRF_queued",
        "otp": "123456",
    },
    options=RequestOptions(
        access_token="sk_test_override",
        headers={"x-request-id": "req-123"},
    ),
)
```

For M-PESA and SasaPay, `force_token_refresh=True` forces a fresh OAuth lookup on that request:

```python
result = mpesa.stk_push(
    payload,
    options=RequestOptions(force_token_refresh=True),
)
```

### Retries

```python
from noriapay import RetryPolicy

retry = RetryPolicy(
    max_attempts=3,
    retry_methods=("GET", "POST"),
    retry_on_statuses=(500, 502, 503, 504),
    retry_on_network_error=True,
    base_delay_seconds=0.25,
    max_delay_seconds=2.0,
    backoff_multiplier=2.0,
)

paystack = PaystackClient.from_env(retry=retry)
```

You can also attach retry rules per request:

```python
response = sasapay.request_payment(
    payload,
    options=RequestOptions(
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("POST",),
            retry_on_statuses=(500,),
        )
    ),
)
```

### Hooks

```python
from noriapay import Hooks, MpesaClient


def before_request(context) -> None:
    context.headers["x-trace-id"] = "trace-123"


def after_response(context) -> None:
    print(context.method, context.url, context.response_body)


def on_error(context) -> None:
    print("request failed", context.error)


mpesa = MpesaClient.from_env(
    hooks=Hooks(
        before_request=before_request,
        after_response=after_response,
        on_error=on_error,
    )
)
```

Hook context objects are:

- `BeforeRequestContext`
- `AfterResponseContext`
- `ErrorContext`

### Inject Your Own `httpx` Client

```python
import httpx
from noriapay import MpesaClient

http_client = httpx.Client(
    headers={"x-app-name": "billing-service"},
    verify=True,
)

mpesa = MpesaClient.from_env(client=http_client)
```

Sync constructors accept `client=` and keep `session=` as a backward-compatible alias.

Async example:

```python
import httpx
from noriapay import AsyncPaystackClient

http_client = httpx.AsyncClient(headers={"x-app-name": "billing-service"})
paystack = AsyncPaystackClient.from_env(client=http_client)
```

### Use A Custom OAuth Token Provider

`MpesaClient` and `SasaPayClient` can use any object that implements `get_access_token(force_refresh=False)`. The async clients accept an async version of the same contract.

Using the built-in token providers directly:

```python
from noriapay import ClientCredentialsTokenProvider, MpesaClient

provider = ClientCredentialsTokenProvider(
    token_url="https://sandbox.safaricom.co.ke/oauth/v1/generate",
    client_id="consumer-key",
    client_secret="consumer-secret",
    query={"grant_type": "client_credentials"},
)

mpesa = MpesaClient(token_provider=provider, environment="sandbox")
```

```python
from noriapay import AsyncClientCredentialsTokenProvider, AsyncSasaPayClient

provider = AsyncClientCredentialsTokenProvider(
    token_url="https://sandbox.sasapay.app/api/v1/auth/token/",
    client_id="client-id",
    client_secret="client-secret",
    query={"grant_type": "client_credentials"},
)

sasapay = AsyncSasaPayClient(
    token_provider=provider,
    environment="sandbox",
)
```

### Error Handling

```python
from noriapay import (
    ApiError,
    AuthenticationError,
    ConfigurationError,
    NetworkError,
    TimeoutError,
    WebhookVerificationError,
)

try:
    response = paystack.verify_transaction("order-123")
except ConfigurationError:
    ...
except AuthenticationError:
    ...
except TimeoutError:
    ...
except NetworkError:
    ...
except ApiError as error:
    print(error.status_code, error.response_body)
except WebhookVerificationError:
    ...
```

## Shared API Reference

### Core Shared Types

```python
Environment = Literal["sandbox", "production"]

class AccessTokenProvider(Protocol):
    def get_access_token(self, force_refresh: bool = False) -> str: ...


class AsyncAccessTokenProvider(Protocol):
    async def get_access_token(self, force_refresh: bool = False) -> str: ...


AccessToken(
    access_token: str,
    expires_in: int,
    token_type: str | None = None,
    scope: str | None = None,
    raw: dict[str, Any] = {},
)
```

### Request And Retry Types

```python
RequestOptions(
    headers=None,
    timeout_seconds=None,
    retry=None,
    access_token=None,
    force_token_refresh=False,
)

RetryDecisionContext(
    attempt: int,
    max_attempts: int,
    method: str,
    url: str,
    status: int | None = None,
    error: object = None,
)

RetryPolicy(
    max_attempts=1,
    retry_methods=(),
    retry_on_statuses=(),
    retry_on_network_error=False,
    base_delay_seconds=0.0,
    max_delay_seconds=60.0,
    backoff_multiplier=2.0,
    should_retry=None,
)
```

### Hooks

```python
Hooks(
    before_request=None,
    after_response=None,
    on_error=None,
)
```

`before_request`, `after_response`, and `on_error` each accept a single callable or a sequence of callables.

### Built-In Token Providers

```python
ClientCredentialsTokenProvider(
    token_url,
    client_id,
    client_secret,
    client=None,
    session=None,
    timeout_seconds=None,
    query=None,
    cache_skew_seconds=60.0,
    map_response=None,
)

provider.get_token(force_refresh=False)
provider.get_access_token(force_refresh=False)
provider.clear_cache()
provider.close()
```

```python
AsyncClientCredentialsTokenProvider(
    token_url,
    client_id,
    client_secret,
    client=None,
    timeout_seconds=None,
    query=None,
    cache_skew_seconds=60.0,
    map_response=None,
)

await provider.get_token(force_refresh=False)
await provider.get_access_token(force_refresh=False)
provider.clear_cache()
await provider.aclose()
```

### Webhook Helpers

```python
PAYSTACK_WEBHOOK_IPS
compute_paystack_signature(raw_body, secret_key)
verify_paystack_signature(raw_body, signature, secret_key)
require_paystack_signature(raw_body, signature, secret_key)
verify_source_ip(source_ip, allowed_ips)
require_source_ip(source_ip, allowed_ips)
```

### Exceptions

- `NoriapayError`
- `ConfigurationError`
- `AuthenticationError`
- `TimeoutError`
- `NetworkError`
- `ApiError`
- `WebhookVerificationError`

## Public Export Index

### Shared Exports

- `AccessToken`
- `AccessTokenProvider`
- `AfterResponseContext`
- `ApiError`
- `AsyncAccessTokenProvider`
- `AsyncClientCredentialsTokenProvider`
- `AuthenticationError`
- `BeforeRequestContext`
- `ClientCredentialsTokenProvider`
- `ConfigurationError`
- `Environment`
- `ErrorContext`
- `Hooks`
- `NetworkError`
- `NoriapayError`
- `RequestOptions`
- `RetryDecisionContext`
- `RetryPolicy`
- `TimeoutError`
- `WebhookVerificationError`

### M-PESA Exports

- `MPESA_BASE_URLS`
- `AsyncMpesaClient`
- `MpesaAccountBalanceRequest`
- `MpesaApiResponse`
- `MpesaB2BRequest`
- `MpesaB2CRequest`
- `MpesaClient`
- `MpesaQrCodeRequest`
- `MpesaRegisterC2BUrlsRequest`
- `MpesaReversalRequest`
- `MpesaStkPushRequest`
- `MpesaStkPushResponse`
- `MpesaStkQueryRequest`
- `MpesaTransactionStatusRequest`
- `build_mpesa_stk_password`
- `build_mpesa_timestamp`

### SasaPay Exports

- `SASAPAY_BASE_URL`
- `AsyncSasaPayClient`
- `SasaPayAuthResponse`
- `SasaPayB2BRequest`
- `SasaPayB2BResponse`
- `SasaPayB2CRequest`
- `SasaPayB2CResponse`
- `SasaPayC2BCallback`
- `SasaPayC2BIpn`
- `SasaPayClient`
- `SasaPayProcessPaymentRequest`
- `SasaPayProcessPaymentResponse`
- `SasaPayRequestPaymentRequest`
- `SasaPayRequestPaymentResponse`
- `SasaPayTransferCallback`

### Paystack Exports

- `PAYSTACK_BASE_URL`
- `AsyncPaystackClient`
- `PaystackApiResponse`
- `PaystackBank`
- `PaystackClient`
- `PaystackCreateTransferRecipientRequest`
- `PaystackCreateTransferRecipientResponse`
- `PaystackFinalizeTransferRequest`
- `PaystackFinalizeTransferResponse`
- `PaystackInitializeTransactionData`
- `PaystackInitializeTransactionRequest`
- `PaystackInitializeTransactionResponse`
- `PaystackInitiateTransferRequest`
- `PaystackInitiateTransferResponse`
- `PaystackListBanksQuery`
- `PaystackListBanksResponse`
- `PaystackResolveAccountData`
- `PaystackResolveAccountResponse`
- `PaystackTransaction`
- `PaystackTransfer`
- `PaystackTransferRecipient`
- `PaystackTransferRecipientDetails`
- `PaystackVerifyTransactionResponse`
- `PaystackVerifyTransferResponse`

### Webhook Helper Exports

- `PAYSTACK_WEBHOOK_IPS`
- `compute_paystack_signature`
- `require_paystack_signature`
- `require_source_ip`
- `verify_paystack_signature`
- `verify_source_ip`

## Live Sandbox Checks

The package includes opt-in integration tests against live sandbox or test credentials.

```bash
export RUN_LIVE_SANDBOX_TESTS=1
uv run pytest -m integration
```

Credentials expected by the integration suite:

- M-PESA: `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`
- SasaPay: `SASAPAY_CLIENT_ID`, `SASAPAY_CLIENT_SECRET`
- Paystack: `PAYSTACK_SECRET_KEY`

Use test or sandbox credentials only.

## Provider Docs

- SasaPay getting started: <https://developer.sasapay.app/docs/getting-started>
- SasaPay authentication: <https://developer.sasapay.app/docs/apis/authentication>
- SasaPay C2B: <https://developer.sasapay.app/docs/apis/c2b>
- SasaPay B2C: <https://developer.sasapay.app/docs/apis/b2c>
- SasaPay B2B: <https://developer.sasapay.app/docs/apis/b2b>
- Paystack API reference: <https://paystack.com/docs/api/>
- Paystack transfer recipient guide: <https://paystack.com/docs/transfers/creating-transfer-recipients/>
- Paystack webhooks: <https://paystack.com/docs/payments/webhooks/>

## Notes

- choose `MpesaClient`, `SasaPayClient`, and `PaystackClient` for blocking code paths
- choose `AsyncMpesaClient`, `AsyncSasaPayClient`, and `AsyncPaystackClient` for `asyncio` applications
- sync clients use `httpx.Client`; async clients use `httpx.AsyncClient`
- sync constructors accept `client=` and also keep `session=` as a backward-compatible alias
- provider JSON is returned as parsed Python data structures
- the package uses `TypedDict` payload and response models for editor guidance, not full runtime schema validation
