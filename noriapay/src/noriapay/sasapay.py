from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict

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
from .utils import to_amount_string

SASAPAY_BASE_URL = "https://sandbox.sasapay.app/api/v1"


class SasaPayAuthResponse(TypedDict, total=False):
    status: bool
    detail: str
    access_token: str
    expires_in: int
    token_type: str
    scope: str


class SasaPayRequestPaymentRequest(TypedDict):
    MerchantCode: str
    NetworkCode: str
    Currency: str
    Amount: str | int | float
    PhoneNumber: str
    AccountReference: str
    TransactionDesc: str
    CallBackURL: str


class SasaPayRequestPaymentResponse(TypedDict, total=False):
    status: bool
    detail: str
    PaymentGateway: str
    MerchantRequestID: str
    CheckoutRequestID: str
    TransactionReference: str
    ResponseCode: str
    ResponseDescription: str
    CustomerMessage: str


class SasaPayProcessPaymentRequest(TypedDict):
    MerchantCode: str
    CheckoutRequestID: str
    VerificationCode: str


class SasaPayProcessPaymentResponse(TypedDict, total=False):
    status: bool
    detail: str


class SasaPayB2CRequest(TypedDict):
    MerchantCode: str
    Amount: str | int | float
    Currency: str
    MerchantTransactionReference: str
    ReceiverNumber: str
    Channel: str
    Reason: str
    CallBackURL: str


class SasaPayB2CResponse(TypedDict, total=False):
    status: bool
    detail: str
    B2CRequestID: str
    ConversationID: str
    OriginatorConversationID: str
    ResponseCode: str
    TransactionCharges: str
    ResponseDescription: str


class SasaPayB2BRequest(TypedDict):
    MerchantCode: str
    MerchantTransactionReference: str
    Currency: str
    Amount: str | int | float
    ReceiverMerchantCode: str
    AccountReference: str
    ReceiverAccountType: str
    NetworkCode: str
    Reason: str
    CallBackURL: str


class SasaPayB2BResponse(TypedDict, total=False):
    status: bool
    detail: str
    B2BRequestID: str
    ConversationID: str
    OriginatorConversationID: str
    TransactionCharges: str
    ResponseCode: str
    ResponseDescription: str


class SasaPayC2BCallback(TypedDict):
    MerchantRequestID: str
    CheckoutRequestID: str
    PaymentRequestID: str
    ResultCode: str
    ResultDesc: str
    SourceChannel: str
    TransAmount: str
    RequestedAmount: str
    Paid: bool
    BillRefNumber: str
    TransactionDate: str
    CustomerMobile: str
    TransactionCode: str
    ThirdPartyTransID: str


class SasaPayC2BIpn(TypedDict):
    MerchantCode: str
    BusinessShortCode: str
    InvoiceNumber: str
    PaymentMethod: str
    TransID: str
    ThirdPartyTransID: str
    FullName: str
    FirstName: str
    MiddleName: str
    LastName: str
    TransactionType: str
    MSISDN: str
    OrgAccountBalance: str
    TransAmount: str
    TransTime: str
    BillRefNumber: str


class SasaPayTransferCallback(TypedDict, total=False):
    MerchantCode: str
    DestinationChannel: str
    RecipientName: str
    RecipientAccountNumber: str
    ResultCode: str
    ResultDesc: str
    SourceChannel: str
    SasaPayTransactionCode: str
    CheckoutRequestID: str
    SasaPayTransactionID: str
    ThirdPartyTransactionCode: str
    TransactionAmount: str
    TransactionCharge: NotRequired[str]
    TransactionCharges: NotRequired[str]
    MerchantRequestID: str
    MerchantTransactionReference: str
    TransactionDate: str
    MerchantAccountBalance: str
    LinkedTransactionCode: NotRequired[str]


class SasaPayClient:
    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "SASAPAY_",
        environ: Mapping[str, str] | None = None,
        token_provider: AccessTokenProvider | None = None,
        client: httpx.Client | Any | None = None,
        session: httpx.Client | Any | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> SasaPayClient:
        return cls(
            client_id=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CLIENT_ID", environ=environ)
            ),
            client_secret=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CLIENT_SECRET", environ=environ)
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
        client_id: str | None = None,
        client_secret: str | None = None,
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

        resolved_base_url = _resolve_sasapay_base_url(environment=environment, base_url=base_url)
        self._http = HttpClient(
            base_url=resolved_base_url,
            client=self._client,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )
        self._tokens = _resolve_sasapay_token_provider(
            token_provider=token_provider,
            client_id=client_id,
            client_secret=client_secret,
            client=self._client,
            timeout_seconds=timeout_seconds,
            token_cache_skew_seconds=token_cache_skew_seconds,
            base_url=resolved_base_url,
        )

    def get_access_token(self, force_refresh: bool = False) -> str:
        return self._tokens.get_access_token(force_refresh=force_refresh)

    def request_payment(
        self,
        payload: SasaPayRequestPaymentRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayRequestPaymentResponse:
        return self._authorized_request(
            "/payments/request-payment/",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def process_payment(
        self,
        payload: SasaPayProcessPaymentRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayProcessPaymentResponse:
        return self._authorized_request("/payments/process-payment/", dict(payload), options)

    def b2c_payment(
        self,
        payload: SasaPayB2CRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayB2CResponse:
        return self._authorized_request(
            "/payments/b2c/",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def b2b_payment(
        self,
        payload: SasaPayB2BRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayB2BResponse:
        return self._authorized_request(
            "/payments/b2b/",
            _with_amount(payload, ("Amount",)),
            options,
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def __enter__(self) -> SasaPayClient:
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


class AsyncSasaPayClient:
    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "SASAPAY_",
        environ: Mapping[str, str] | None = None,
        token_provider: AsyncAccessTokenProvider | None = None,
        client: httpx.AsyncClient | Any | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        hooks: Hooks | None = None,
    ) -> AsyncSasaPayClient:
        return cls(
            client_id=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CLIENT_ID", environ=environ)
            ),
            client_secret=(
                None
                if token_provider is not None
                else get_required_env(f"{prefix}CLIENT_SECRET", environ=environ)
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
        client_id: str | None = None,
        client_secret: str | None = None,
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

        resolved_base_url = _resolve_sasapay_base_url(environment=environment, base_url=base_url)
        self._http = AsyncHttpClient(
            base_url=resolved_base_url,
            client=self._client,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
            retry=retry,
            hooks=hooks,
        )
        self._tokens = _resolve_async_sasapay_token_provider(
            token_provider=token_provider,
            client_id=client_id,
            client_secret=client_secret,
            client=self._client,
            timeout_seconds=timeout_seconds,
            token_cache_skew_seconds=token_cache_skew_seconds,
            base_url=resolved_base_url,
        )

    async def get_access_token(self, force_refresh: bool = False) -> str:
        return await self._tokens.get_access_token(force_refresh=force_refresh)

    async def request_payment(
        self,
        payload: SasaPayRequestPaymentRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayRequestPaymentResponse:
        return await self._authorized_request(
            "/payments/request-payment/",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def process_payment(
        self,
        payload: SasaPayProcessPaymentRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayProcessPaymentResponse:
        return await self._authorized_request("/payments/process-payment/", dict(payload), options)

    async def b2c_payment(
        self,
        payload: SasaPayB2CRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayB2CResponse:
        return await self._authorized_request(
            "/payments/b2c/",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def b2b_payment(
        self,
        payload: SasaPayB2BRequest,
        options: RequestOptions | None = None,
    ) -> SasaPayB2BResponse:
        return await self._authorized_request(
            "/payments/b2b/",
            _with_amount(payload, ("Amount",)),
            options,
        )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncSasaPayClient:
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


def _resolve_sasapay_base_url(*, environment: Environment, base_url: str | None) -> str:
    if base_url:
        return base_url

    if environment == "sandbox":
        return SASAPAY_BASE_URL

    raise ConfigurationError(
        "SasaPay production base_url must be provided explicitly. "
        "The reviewed docs clearly document the sandbox host but do "
        "not clearly state a production API host."
    )


def _resolve_sasapay_token_provider(
    *,
    token_provider: AccessTokenProvider | None,
    client_id: str | None,
    client_secret: str | None,
    client: httpx.Client | Any,
    timeout_seconds: float | None,
    token_cache_skew_seconds: float,
    base_url: str,
) -> AccessTokenProvider:
    if token_provider is not None:
        return token_provider

    if not client_id or not client_secret:
        raise ConfigurationError(
            "SasaPayClient requires either client_id and client_secret, or token_provider."
        )

    return ClientCredentialsTokenProvider(
        token_url=f"{base_url}/auth/token/",
        client_id=client_id,
        client_secret=client_secret,
        client=client,
        timeout_seconds=timeout_seconds,
        query={"grant_type": "client_credentials"},
        cache_skew_seconds=token_cache_skew_seconds,
    )


def _resolve_async_sasapay_token_provider(
    *,
    token_provider: AsyncAccessTokenProvider | None,
    client_id: str | None,
    client_secret: str | None,
    client: httpx.AsyncClient | Any,
    timeout_seconds: float | None,
    token_cache_skew_seconds: float,
    base_url: str,
) -> AsyncAccessTokenProvider:
    if token_provider is not None:
        return token_provider

    if not client_id or not client_secret:
        raise ConfigurationError(
            "AsyncSasaPayClient requires either client_id and client_secret, or token_provider."
        )

    return AsyncClientCredentialsTokenProvider(
        token_url=f"{base_url}/auth/token/",
        client_id=client_id,
        client_secret=client_secret,
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
