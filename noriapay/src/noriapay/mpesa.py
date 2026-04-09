from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import datetime
from typing import Any, NotRequired, Required, TypedDict

import httpx

from .config import (
    get_env_environment,
    get_env_float,
    get_optional_env,
    get_required_env,
)
from .exceptions import ConfigurationError
from .http import AsyncHttpClient, HttpClient
from .oauth import AsyncClientCredentialsTokenProvider, ClientCredentialsTokenProvider
from .types import (
    AccessTokenProvider,
    AsyncAccessTokenProvider,
    Environment,
    Hooks,
    HttpRequestOptions,
    RequestOptions,
    RetryPolicy,
)
from .utils import build_mpesa_timestamp_value, to_amount_string

MPESA_BASE_URLS: dict[Environment, str] = {
    "sandbox": "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}


class MpesaApiResponse(TypedDict, total=False):
    ConversationID: str
    OriginatorConversationID: str
    ResponseCode: str
    ResponseDescription: str
    CustomerMessage: str
    errorCode: str
    errorMessage: str


class MpesaStkPushRequest(TypedDict):
    BusinessShortCode: str
    Password: str
    Timestamp: str
    TransactionType: str
    Amount: str | int | float
    PartyA: str
    PartyB: str
    PhoneNumber: str
    CallBackURL: str
    AccountReference: str
    TransactionDesc: str


class MpesaStkPushResponse(MpesaApiResponse, total=False):
    MerchantRequestID: str
    CheckoutRequestID: str


class MpesaStkQueryRequest(TypedDict):
    BusinessShortCode: str
    Password: str
    Timestamp: str
    CheckoutRequestID: str


class MpesaRegisterC2BUrlsRequest(TypedDict):
    ShortCode: str
    ResponseType: str
    ConfirmationURL: str
    ValidationURL: str


class MpesaB2CRequest(TypedDict, total=False):
    InitiatorName: Required[str]
    SecurityCredential: Required[str]
    CommandID: Required[str]
    Amount: Required[str | int | float]
    PartyA: Required[str]
    PartyB: Required[str]
    Remarks: Required[str]
    QueueTimeOutURL: Required[str]
    ResultURL: Required[str]
    Occasion: NotRequired[str]


class MpesaB2BRequest(TypedDict):
    Initiator: str
    SecurityCredential: str
    CommandID: str
    Amount: str | int | float
    PartyA: str
    PartyB: str
    Remarks: str
    AccountReference: str
    QueueTimeOutURL: str
    ResultURL: str


class MpesaReversalRequest(TypedDict, total=False):
    Initiator: Required[str]
    SecurityCredential: Required[str]
    CommandID: Required[str]
    TransactionID: Required[str]
    Amount: Required[str | int | float]
    ReceiverParty: Required[str]
    RecieverIdentifierType: Required[str]
    ResultURL: Required[str]
    QueueTimeOutURL: Required[str]
    Remarks: Required[str]
    Occasion: NotRequired[str]


class MpesaTransactionStatusRequest(TypedDict, total=False):
    Initiator: Required[str]
    SecurityCredential: Required[str]
    CommandID: Required[str]
    TransactionID: Required[str]
    PartyA: Required[str]
    IdentifierType: Required[str]
    ResultURL: Required[str]
    QueueTimeOutURL: Required[str]
    Remarks: Required[str]
    Occasion: NotRequired[str]


class MpesaAccountBalanceRequest(TypedDict):
    Initiator: str
    SecurityCredential: str
    CommandID: str
    PartyA: str
    IdentifierType: str
    ResultURL: str
    QueueTimeOutURL: str
    Remarks: str


class MpesaQrCodeRequest(TypedDict):
    MerchantName: str
    MerchantShortCode: str
    Amount: str | int | float
    QRType: str


class MpesaClient:
    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "MPESA_",
        environ: Mapping[str, str] | None = None,
        token_provider: AccessTokenProvider | None = None,
        client: httpx.Client | Any | None = None,
        session: httpx.Client | Any | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> MpesaClient:
        return cls(
            consumer_key=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CONSUMER_KEY", environ=environ)
            ),
            consumer_secret=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CONSUMER_SECRET", environ=environ)
            ),
            token_provider=token_provider,
            environment=get_env_environment(f"{prefix}ENVIRONMENT", environ=environ),
            base_url=get_optional_env(f"{prefix}BASE_URL", environ=environ),
            client=client,
            session=session,
            timeout_seconds=get_env_float(f"{prefix}TIMEOUT_SECONDS", environ=environ),
            token_cache_skew_seconds=(
                get_env_float(f"{prefix}TOKEN_CACHE_SKEW_SECONDS", environ=environ) or 60.0
            ),
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )

    def __init__(
        self,
        *,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        token_provider: AccessTokenProvider | None = None,
        environment: Environment = "sandbox",
        base_url: str | None = None,
        client: httpx.Client | Any | None = None,
        session: httpx.Client | Any | None = None,
        timeout_seconds: float | None = None,
        token_cache_skew_seconds: float = 60.0,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> None:
        resolved_client = _resolve_sync_client(client, session)
        self._client = resolved_client
        self._owns_client = False
        if self._client is None:
            self._client = httpx.Client()
            self._owns_client = True

        resolved_base_url = base_url or MPESA_BASE_URLS[environment]
        self._http = HttpClient(
            base_url=resolved_base_url,
            client=self._client,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )
        self._tokens = _resolve_mpesa_token_provider(
            token_provider=token_provider,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            client=self._client,
            timeout_seconds=timeout_seconds,
            token_cache_skew_seconds=token_cache_skew_seconds,
            base_url=resolved_base_url,
        )

    def get_access_token(self, force_refresh: bool = False) -> str:
        return self._tokens.get_access_token(force_refresh=force_refresh)

    def stk_push(
        self,
        payload: MpesaStkPushRequest,
        options: RequestOptions | None = None,
    ) -> MpesaStkPushResponse:
        return self._authorized_request(
            "/mpesa/stkpush/v1/processrequest",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def stk_push_query(
        self,
        payload: MpesaStkQueryRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return self._authorized_request("/mpesa/stkpushquery/v1/query", payload, options)

    def register_c2b_urls(
        self,
        payload: MpesaRegisterC2BUrlsRequest,
        *,
        version: str = "v2",
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return self._authorized_request(f"/mpesa/c2b/{version}/registerurl", payload, options)

    def b2c_payment(
        self, payload: MpesaB2CRequest, options: RequestOptions | None = None
    ) -> MpesaApiResponse:
        return self._authorized_request(
            "/mpesa/b2c/v1/paymentrequest",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def b2b_payment(
        self, payload: MpesaB2BRequest, options: RequestOptions | None = None
    ) -> MpesaApiResponse:
        return self._authorized_request(
            "/mpesa/b2b/v1/paymentrequest",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def reversal(
        self, payload: MpesaReversalRequest, options: RequestOptions | None = None
    ) -> MpesaApiResponse:
        return self._authorized_request(
            "/mpesa/reversal/v1/request",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def transaction_status(
        self,
        payload: MpesaTransactionStatusRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return self._authorized_request("/mpesa/transactionstatus/v1/query", payload, options)

    def account_balance(
        self,
        payload: MpesaAccountBalanceRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return self._authorized_request("/mpesa/accountbalance/v1/query", payload, options)

    def generate_qr_code(
        self,
        payload: MpesaQrCodeRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return self._authorized_request(
            "/mpesa/qrcode/v1/generate",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def __enter__(self) -> MpesaClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _authorized_request(
        self,
        path: str,
        payload: dict[str, Any],
        options: RequestOptions | None,
    ) -> Any:
        request_options = options or RequestOptions()
        access_token = request_options.access_token or self._tokens.get_access_token(
            force_refresh=request_options.force_token_refresh
        )
        headers = dict(request_options.headers or {})
        headers["authorization"] = f"Bearer {access_token}"
        headers["accept"] = "application/json"
        return self._http.request(
            HttpRequestOptions(
                path=path,
                method="POST",
                headers=headers,
                body=payload,
                timeout_seconds=request_options.timeout_seconds,
                retry=request_options.retry,
            )
        )


class AsyncMpesaClient:
    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "MPESA_",
        environ: Mapping[str, str] | None = None,
        token_provider: AsyncAccessTokenProvider | None = None,
        client: httpx.AsyncClient | Any | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> AsyncMpesaClient:
        return cls(
            consumer_key=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CONSUMER_KEY", environ=environ)
            ),
            consumer_secret=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CONSUMER_SECRET", environ=environ)
            ),
            token_provider=token_provider,
            environment=get_env_environment(f"{prefix}ENVIRONMENT", environ=environ),
            base_url=get_optional_env(f"{prefix}BASE_URL", environ=environ),
            client=client,
            timeout_seconds=get_env_float(f"{prefix}TIMEOUT_SECONDS", environ=environ),
            token_cache_skew_seconds=(
                get_env_float(f"{prefix}TOKEN_CACHE_SKEW_SECONDS", environ=environ) or 60.0
            ),
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )

    def __init__(
        self,
        *,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        token_provider: AsyncAccessTokenProvider | None = None,
        environment: Environment = "sandbox",
        base_url: str | None = None,
        client: httpx.AsyncClient | Any | None = None,
        timeout_seconds: float | None = None,
        token_cache_skew_seconds: float = 60.0,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> None:
        self._client = client
        self._owns_client = False
        if self._client is None:
            self._client = httpx.AsyncClient()
            self._owns_client = True

        resolved_base_url = base_url or MPESA_BASE_URLS[environment]
        self._http = AsyncHttpClient(
            base_url=resolved_base_url,
            client=self._client,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )
        self._tokens = _resolve_async_mpesa_token_provider(
            token_provider=token_provider,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            client=self._client,
            timeout_seconds=timeout_seconds,
            token_cache_skew_seconds=token_cache_skew_seconds,
            base_url=resolved_base_url,
        )

    async def get_access_token(self, force_refresh: bool = False) -> str:
        return await self._tokens.get_access_token(force_refresh=force_refresh)

    async def stk_push(
        self,
        payload: MpesaStkPushRequest,
        options: RequestOptions | None = None,
    ) -> MpesaStkPushResponse:
        return await self._authorized_request(
            "/mpesa/stkpush/v1/processrequest",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def stk_push_query(
        self,
        payload: MpesaStkQueryRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return await self._authorized_request("/mpesa/stkpushquery/v1/query", payload, options)

    async def register_c2b_urls(
        self,
        payload: MpesaRegisterC2BUrlsRequest,
        *,
        version: str = "v2",
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return await self._authorized_request(
            f"/mpesa/c2b/{version}/registerurl",
            payload,
            options,
        )

    async def b2c_payment(
        self, payload: MpesaB2CRequest, options: RequestOptions | None = None
    ) -> MpesaApiResponse:
        return await self._authorized_request(
            "/mpesa/b2c/v1/paymentrequest",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def b2b_payment(
        self, payload: MpesaB2BRequest, options: RequestOptions | None = None
    ) -> MpesaApiResponse:
        return await self._authorized_request(
            "/mpesa/b2b/v1/paymentrequest",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def reversal(
        self, payload: MpesaReversalRequest, options: RequestOptions | None = None
    ) -> MpesaApiResponse:
        return await self._authorized_request(
            "/mpesa/reversal/v1/request",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def transaction_status(
        self,
        payload: MpesaTransactionStatusRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return await self._authorized_request("/mpesa/transactionstatus/v1/query", payload, options)

    async def account_balance(
        self,
        payload: MpesaAccountBalanceRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return await self._authorized_request("/mpesa/accountbalance/v1/query", payload, options)

    async def generate_qr_code(
        self,
        payload: MpesaQrCodeRequest,
        options: RequestOptions | None = None,
    ) -> MpesaApiResponse:
        return await self._authorized_request(
            "/mpesa/qrcode/v1/generate",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncMpesaClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def _authorized_request(
        self,
        path: str,
        payload: dict[str, Any],
        options: RequestOptions | None,
    ) -> Any:
        request_options = options or RequestOptions()
        access_token = request_options.access_token or await self._tokens.get_access_token(
            force_refresh=request_options.force_token_refresh
        )
        headers = dict(request_options.headers or {})
        headers["authorization"] = f"Bearer {access_token}"
        headers["accept"] = "application/json"
        return await self._http.request(
            HttpRequestOptions(
                path=path,
                method="POST",
                headers=headers,
                body=payload,
                timeout_seconds=request_options.timeout_seconds,
                retry=request_options.retry,
            )
        )


def build_mpesa_timestamp(dt: datetime | None = None) -> str:
    return build_mpesa_timestamp_value(dt)


def build_mpesa_stk_password(*, business_short_code: str, passkey: str, timestamp: str) -> str:
    raw = f"{business_short_code}{passkey}{timestamp}".encode()
    return base64.b64encode(raw).decode("ascii")


def _resolve_mpesa_token_provider(
    *,
    token_provider: AccessTokenProvider | None,
    consumer_key: str | None,
    consumer_secret: str | None,
    client: httpx.Client | Any,
    timeout_seconds: float | None,
    token_cache_skew_seconds: float,
    base_url: str,
) -> AccessTokenProvider:
    if token_provider is not None:
        return token_provider

    if not consumer_key or not consumer_secret:
        raise ConfigurationError(
            "MpesaClient requires either consumer_key and consumer_secret, or token_provider."
        )

    return ClientCredentialsTokenProvider(
        token_url=f"{base_url}/oauth/v1/generate",
        client_id=consumer_key,
        client_secret=consumer_secret,
        client=client,
        timeout_seconds=timeout_seconds,
        query={"grant_type": "client_credentials"},
        cache_skew_seconds=token_cache_skew_seconds,
    )


def _resolve_async_mpesa_token_provider(
    *,
    token_provider: AsyncAccessTokenProvider | None,
    consumer_key: str | None,
    consumer_secret: str | None,
    client: httpx.AsyncClient | Any,
    timeout_seconds: float | None,
    token_cache_skew_seconds: float,
    base_url: str,
) -> AsyncAccessTokenProvider:
    if token_provider is not None:
        return token_provider

    if not consumer_key or not consumer_secret:
        raise ConfigurationError(
            "AsyncMpesaClient requires either consumer_key and consumer_secret, or token_provider."
        )

    return AsyncClientCredentialsTokenProvider(
        token_url=f"{base_url}/oauth/v1/generate",
        client_id=consumer_key,
        client_secret=consumer_secret,
        client=client,
        timeout_seconds=timeout_seconds,
        query={"grant_type": "client_credentials"},
        cache_skew_seconds=token_cache_skew_seconds,
    )


def _resolve_sync_client(
    client: httpx.Client | Any | None,
    session: httpx.Client | Any | None,
) -> httpx.Client | Any | None:
    if client is not None and session is not None and client is not session:
        raise ConfigurationError("Provide only one of client or session.")
    return client if client is not None else session


def _with_amount(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    normalized = dict(payload)
    for field in fields:
        value = normalized.get(field)
        if isinstance(value, (str, int, float)):
            normalized[field] = to_amount_string(value)
    return normalized
