from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, NotRequired, Required, TypedDict

import httpx

from .config import get_env_float, get_optional_env, get_required_env
from .exceptions import ConfigurationError
from .http import AsyncHttpClient, HttpClient
from .types import Hooks, HttpRequestOptions, RequestOptions, RetryPolicy

PAYSTACK_BASE_URL = "https://api.paystack.co"

PaystackBearer = Literal["account", "subaccount"]
PaystackPaymentChannel = Literal[
    "card",
    "bank",
    "apple_pay",
    "ussd",
    "qr",
    "mobile_money",
    "bank_transfer",
    "eft",
    "capitec_pay",
    "payattitude",
]
PaystackRecipientType = Literal[
    "authorization",
    "basa",
    "ghipss",
    "kepss",
    "mobile_money",
    "mobile_money_business",
    "nuban",
]


class PaystackApiResponse(TypedDict, total=False):
    status: bool
    message: str


class PaystackInitializeTransactionRequest(TypedDict, total=False):
    amount: Required[str | int]
    email: Required[str]
    channels: NotRequired[Sequence[PaystackPaymentChannel]]
    currency: NotRequired[str]
    reference: NotRequired[str]
    callback_url: NotRequired[str]
    plan: NotRequired[str]
    invoice_limit: NotRequired[int]
    metadata: NotRequired[object]
    split_code: NotRequired[str]
    subaccount: NotRequired[str]
    transaction_charge: NotRequired[int]
    bearer: NotRequired[PaystackBearer]


class PaystackInitializeTransactionData(TypedDict, total=False):
    authorization_url: str
    access_code: str
    reference: str


class PaystackInitializeTransactionResponse(PaystackApiResponse, total=False):
    data: PaystackInitializeTransactionData


class PaystackTransactionAuthorization(TypedDict, total=False):
    authorization_code: str
    bin: str
    last4: str
    exp_month: str
    exp_year: str
    channel: str
    card_type: str
    bank: str
    country_code: str
    brand: str
    reusable: bool
    signature: str
    account_name: str | None


class PaystackTransactionCustomer(TypedDict, total=False):
    id: int
    first_name: str | None
    last_name: str | None
    email: str
    customer_code: str
    phone: str | None
    metadata: object
    risk_action: str
    international_format_phone: str | None


class PaystackTransaction(TypedDict, total=False):
    id: int
    domain: str
    status: str
    reference: str
    receipt_number: str | None
    amount: int
    message: str | None
    gateway_response: str
    paid_at: str
    created_at: str
    channel: str
    currency: str
    ip_address: str
    metadata: object
    log: object
    fees: int
    fees_split: object
    authorization: PaystackTransactionAuthorization
    customer: PaystackTransactionCustomer
    plan: object
    split: object
    order_id: object
    paidAt: str
    createdAt: str
    requested_amount: int
    pos_transaction_data: object
    source: object
    fees_breakdown: object
    connect: object
    transaction_date: str
    plan_object: object
    subaccount: object


class PaystackVerifyTransactionResponse(PaystackApiResponse, total=False):
    data: PaystackTransaction


class PaystackBank(TypedDict, total=False):
    name: str
    slug: str
    code: str
    longcode: str
    gateway: str | None
    pay_with_bank: bool
    active: bool
    is_deleted: bool | None
    country: str
    currency: str
    type: str
    id: int
    createdAt: str
    updatedAt: str


class PaystackCursorMeta(TypedDict, total=False):
    total: int
    skipped: int
    perPage: int
    page: int
    pageCount: int
    next: str | None
    previous: str | None


class PaystackListBanksQuery(TypedDict, total=False):
    country: str
    use_cursor: bool
    perPage: int
    pay_with_bank_transfer: bool
    pay_with_bank: bool
    enabled_for_verification: bool
    next: str
    previous: str
    gateway: str
    type: str
    currency: str
    include_nip_sort_code: bool


class PaystackListBanksResponse(PaystackApiResponse, total=False):
    data: list[PaystackBank]
    meta: PaystackCursorMeta


class PaystackResolveAccountData(TypedDict, total=False):
    account_number: str
    account_name: str
    bank_id: int


class PaystackResolveAccountResponse(PaystackApiResponse, total=False):
    data: PaystackResolveAccountData


class PaystackTransferRecipientDetails(TypedDict, total=False):
    authorization_code: str | None
    account_number: str | None
    account_name: str | None
    bank_code: str | None
    bank_name: str | None


class PaystackTransferRecipient(TypedDict, total=False):
    active: bool
    createdAt: str
    currency: str
    description: str | None
    domain: str
    email: str | None
    id: int
    integration: int
    metadata: object
    name: str
    recipient_code: str
    type: str
    updatedAt: str
    is_deleted: bool
    isDeleted: bool
    details: PaystackTransferRecipientDetails


class PaystackCreateTransferRecipientRequest(TypedDict, total=False):
    type: Required[PaystackRecipientType]
    name: Required[str]
    account_number: NotRequired[str]
    bank_code: NotRequired[str]
    description: NotRequired[str]
    currency: NotRequired[str]
    authorization_code: NotRequired[str]
    email: NotRequired[str]
    metadata: NotRequired[object]


class PaystackCreateTransferRecipientResponse(PaystackApiResponse, total=False):
    data: PaystackTransferRecipient


class PaystackTransfer(TypedDict, total=False):
    transfersessionid: list[object]
    transfertrials: list[object]
    domain: str
    amount: int
    currency: str
    reference: str
    source: str
    source_details: object
    reason: str | None
    status: str
    failures: object
    transfer_code: str
    titan_code: object
    transferred_at: str | None
    id: int
    integration: int
    request: object
    recipient: object
    createdAt: str
    updatedAt: str


class PaystackInitiateTransferRequest(TypedDict, total=False):
    source: Required[str]
    amount: Required[int]
    recipient: Required[str]
    reference: NotRequired[str]
    reason: NotRequired[str]
    currency: NotRequired[str]
    account_reference: NotRequired[str]


class PaystackInitiateTransferResponse(PaystackApiResponse, total=False):
    data: PaystackTransfer


class PaystackFinalizeTransferRequest(TypedDict):
    transfer_code: str
    otp: str


class PaystackFinalizeTransferResponse(PaystackApiResponse, total=False):
    data: PaystackTransfer


class PaystackVerifyTransferResponse(PaystackApiResponse, total=False):
    data: PaystackTransfer


class PaystackClient:
    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "PAYSTACK_",
        environ: Mapping[str, str] | None = None,
        client: httpx.Client | Any | None = None,
        session: httpx.Client | Any | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> PaystackClient:
        return cls(
            secret_key=get_required_env(f"{prefix}SECRET_KEY", environ=environ),
            base_url=get_optional_env(f"{prefix}BASE_URL", environ=environ),
            client=client,
            session=session,
            timeout_seconds=get_env_float(f"{prefix}TIMEOUT_SECONDS", environ=environ),
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | Any | None = None,
        session: httpx.Client | Any | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> None:
        if not secret_key:
            raise ConfigurationError("PaystackClient requires secret_key.")

        resolved_client = _resolve_sync_client(client, session)
        self._client = resolved_client
        self._owns_client = False
        if self._client is None:
            self._client = httpx.Client()
            self._owns_client = True

        self._secret_key = secret_key
        self._http = HttpClient(
            base_url=base_url or PAYSTACK_BASE_URL,
            client=self._client,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )

    def initialize_transaction(
        self,
        payload: PaystackInitializeTransactionRequest,
        options: RequestOptions | None = None,
    ) -> PaystackInitializeTransactionResponse:
        return self._request(
            path="/transaction/initialize",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    def verify_transaction(
        self,
        reference: str,
        options: RequestOptions | None = None,
    ) -> PaystackVerifyTransactionResponse:
        return self._request(
            path=f"/transaction/verify/{reference}",
            method="GET",
            options=options,
        )

    def list_banks(
        self,
        query: PaystackListBanksQuery | None = None,
        options: RequestOptions | None = None,
    ) -> PaystackListBanksResponse:
        return self._request(
            path="/bank",
            method="GET",
            query=query,
            options=options,
        )

    def resolve_account(
        self,
        *,
        account_number: str,
        bank_code: str,
        options: RequestOptions | None = None,
    ) -> PaystackResolveAccountResponse:
        return self._request(
            path="/bank/resolve",
            method="GET",
            query={
                "account_number": account_number,
                "bank_code": bank_code,
            },
            options=options,
        )

    def create_transfer_recipient(
        self,
        payload: PaystackCreateTransferRecipientRequest,
        options: RequestOptions | None = None,
    ) -> PaystackCreateTransferRecipientResponse:
        return self._request(
            path="/transferrecipient",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    def initiate_transfer(
        self,
        payload: PaystackInitiateTransferRequest,
        options: RequestOptions | None = None,
    ) -> PaystackInitiateTransferResponse:
        return self._request(
            path="/transfer",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    def finalize_transfer(
        self,
        payload: PaystackFinalizeTransferRequest,
        options: RequestOptions | None = None,
    ) -> PaystackFinalizeTransferResponse:
        return self._request(
            path="/transfer/finalize_transfer",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    def verify_transfer(
        self,
        reference: str,
        options: RequestOptions | None = None,
    ) -> PaystackVerifyTransferResponse:
        return self._request(
            path=f"/transfer/verify/{reference}",
            method="GET",
            options=options,
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def __enter__(self) -> PaystackClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _request(
        self,
        *,
        path: str,
        method: Literal["GET", "POST"],
        options: RequestOptions | None,
        query: Mapping[str, str | int | float | bool | None] | None = None,
        payload: object = None,
    ) -> Any:
        request_options = options or RequestOptions()
        secret_key = request_options.access_token or self._secret_key
        headers = dict(request_options.headers or {})
        headers["authorization"] = f"Bearer {secret_key}"
        headers["accept"] = "application/json"
        return self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,
                headers=headers,
                query=query,
                body=payload,
                timeout_seconds=request_options.timeout_seconds,
                retry=request_options.retry,
            )
        )


class AsyncPaystackClient:
    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "PAYSTACK_",
        environ: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | Any | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> AsyncPaystackClient:
        return cls(
            secret_key=get_required_env(f"{prefix}SECRET_KEY", environ=environ),
            base_url=get_optional_env(f"{prefix}BASE_URL", environ=environ),
            client=client,
            timeout_seconds=get_env_float(f"{prefix}TIMEOUT_SECONDS", environ=environ),
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | Any | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> None:
        if not secret_key:
            raise ConfigurationError("AsyncPaystackClient requires secret_key.")

        self._client = client
        self._owns_client = False
        if self._client is None:
            self._client = httpx.AsyncClient()
            self._owns_client = True

        self._secret_key = secret_key
        self._http = AsyncHttpClient(
            base_url=base_url or PAYSTACK_BASE_URL,
            client=self._client,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )

    async def initialize_transaction(
        self,
        payload: PaystackInitializeTransactionRequest,
        options: RequestOptions | None = None,
    ) -> PaystackInitializeTransactionResponse:
        return await self._request(
            path="/transaction/initialize",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    async def verify_transaction(
        self,
        reference: str,
        options: RequestOptions | None = None,
    ) -> PaystackVerifyTransactionResponse:
        return await self._request(
            path=f"/transaction/verify/{reference}",
            method="GET",
            options=options,
        )

    async def list_banks(
        self,
        query: PaystackListBanksQuery | None = None,
        options: RequestOptions | None = None,
    ) -> PaystackListBanksResponse:
        return await self._request(
            path="/bank",
            method="GET",
            query=query,
            options=options,
        )

    async def resolve_account(
        self,
        *,
        account_number: str,
        bank_code: str,
        options: RequestOptions | None = None,
    ) -> PaystackResolveAccountResponse:
        return await self._request(
            path="/bank/resolve",
            method="GET",
            query={
                "account_number": account_number,
                "bank_code": bank_code,
            },
            options=options,
        )

    async def create_transfer_recipient(
        self,
        payload: PaystackCreateTransferRecipientRequest,
        options: RequestOptions | None = None,
    ) -> PaystackCreateTransferRecipientResponse:
        return await self._request(
            path="/transferrecipient",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    async def initiate_transfer(
        self,
        payload: PaystackInitiateTransferRequest,
        options: RequestOptions | None = None,
    ) -> PaystackInitiateTransferResponse:
        return await self._request(
            path="/transfer",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    async def finalize_transfer(
        self,
        payload: PaystackFinalizeTransferRequest,
        options: RequestOptions | None = None,
    ) -> PaystackFinalizeTransferResponse:
        return await self._request(
            path="/transfer/finalize_transfer",
            method="POST",
            payload=dict(payload),
            options=options,
        )

    async def verify_transfer(
        self,
        reference: str,
        options: RequestOptions | None = None,
    ) -> PaystackVerifyTransferResponse:
        return await self._request(
            path=f"/transfer/verify/{reference}",
            method="GET",
            options=options,
        )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncPaystackClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def _request(
        self,
        *,
        path: str,
        method: Literal["GET", "POST"],
        options: RequestOptions | None,
        query: Mapping[str, str | int | float | bool | None] | None = None,
        payload: object = None,
    ) -> Any:
        request_options = options or RequestOptions()
        secret_key = request_options.access_token or self._secret_key
        headers = dict(request_options.headers or {})
        headers["authorization"] = f"Bearer {secret_key}"
        headers["accept"] = "application/json"
        return await self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,
                headers=headers,
                query=query,
                body=payload,
                timeout_seconds=request_options.timeout_seconds,
                retry=request_options.retry,
            )
        )


def _resolve_sync_client(
    client: httpx.Client | Any | None,
    session: httpx.Client | Any | None,
) -> httpx.Client | Any | None:
    if client is not None and session is not None and client is not session:
        raise ConfigurationError("Provide only one of client or session.")
    return client if client is not None else session
