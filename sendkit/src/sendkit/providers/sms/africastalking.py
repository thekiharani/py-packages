"""Africa's Talking SMS client (sync and async)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...core.config import EnvLike, get_env_number, get_optional_env, get_required_env
from ...core.errors import ProviderError
from ...core.http import AsyncHttpClient, HttpClient
from ...core.types import HttpRequestOptions, RequestOptions
from ...core.utils import (
    coerce_int,
    coerce_string,
    first_text,
    parse_number_from_text,
    require_string,
    to_object,
)
from ...events import DeliveryEvent
from .types import (
    AfricasTalkingDeliveryReport,
    AfricasTalkingFetchMessagesRequest,
    AfricasTalkingFetchMessagesResult,
    AfricasTalkingIncomingMessage,
    AfricasTalkingPremiumSmsRequest,
    AfricasTalkingSubscriptionRequest,
    AfricasTalkingSubscriptionResult,
    SmsBalance,
    SmsBalanceEntry,
    SmsMessage,
    SmsSendReceipt,
    SmsSendRequest,
    SmsSendResult,
)

AFRICASTALKING_SMS_BASE_URL = "https://api.africastalking.com/version1"
AFRICASTALKING_SANDBOX_SMS_BASE_URL = "https://api.sandbox.africastalking.com/version1"


class _AfricasTalkingSmsClientBase:
    """Shared configuration, payload building, and response parsing."""

    provider_name = "africastalking"

    def __init__(
        self,
        *,
        api_key: str,
        username: str,
        default_sender_id: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> None:
        self.username = require_string(username, "username")
        self._default_sender_id = coerce_string(default_sender_id)
        self._http_options = {
            "base_url": base_url or AFRICASTALKING_SMS_BASE_URL,
            "timeout_seconds": timeout_seconds if timeout_seconds is not None else 30.0,
            "default_headers": {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "apiKey": require_string(api_key, "api_key"),
                **(dict(default_headers) if default_headers else {}),
            },
            "retry": retry,
            "hooks": hooks,
        }

    # -- payload building (pure) -------------------------------------------- #

    def _build_send_payload(
        self, request: SmsSendRequest, messages: list[SmsMessage]
    ) -> dict[str, str]:
        sender_id = first_text(request.sender_id, self._default_sender_id)
        params: dict[str, str] = {
            "username": self.username,
            "to": ",".join(
                require_string(message.recipient, "recipient") for message in messages
            ),
            "message": require_string(messages[0].text if messages else None, "text"),
        }

        if sender_id is not None:
            params["from"] = sender_id

        _apply_provider_options(params, request.provider_options)
        return params

    def _build_premium_payload(self, request: AfricasTalkingPremiumSmsRequest) -> dict[str, str]:
        sender_id = first_text(request.short_code, self._default_sender_id)
        params: dict[str, str] = {
            "username": self.username,
            "to": require_string(request.recipient, "recipient"),
            "message": require_string(request.text, "text"),
            "keyword": require_string(request.keyword, "keyword"),
            "linkId": require_string(request.link_id, "link_id"),
        }

        if sender_id is not None:
            params["from"] = sender_id

        if request.retry_duration_in_hours is not None:
            params["retryDurationInHours"] = str(request.retry_duration_in_hours)

        _apply_provider_options(params, request.provider_options)
        return params

    def _build_subscription_payload(
        self, request: AfricasTalkingSubscriptionRequest
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "username": self.username,
            "phoneNumber": require_string(request.phone_number, "phone_number"),
            "shortCode": require_string(request.short_code, "short_code"),
            "keyword": require_string(request.keyword, "keyword"),
        }
        _apply_provider_options(params, request.provider_options)
        return params

    def _fetch_messages_query(
        self, request: AfricasTalkingFetchMessagesRequest
    ) -> dict[str, Any]:
        return {
            "username": self.username,
            "lastReceivedId": request.last_received_id,
            **_normalize_query_options(request.provider_options),
        }

    def parse_delivery_report(self, payload: Mapping[str, Any]) -> DeliveryEvent | None:
        report = parse_africastalking_delivery_report(payload)

        if report.id is None:
            return None

        return DeliveryEvent(
            channel="sms",
            provider=self.provider_name,
            provider_message_id=report.id,
            recipient=report.phone_number,
            state=_map_delivery_state(report.status),
            provider_status=report.status,
            error_code=report.failure_reason,
            occurred_at=None,
            metadata={
                "networkCode": report.network_code,
                "retryCount": report.retry_count,
            },
            raw=report.raw,
        )

    @classmethod
    def _from_env_kwargs(
        cls,
        *,
        prefix: str,
        env: EnvLike | None,
        base_url: str | None,
        timeout_seconds: float | None,
        default_headers: Mapping[str, str] | None,
        retry: object,
        hooks: object,
    ) -> dict[str, Any]:
        return {
            "api_key": _required_env_with_fallback(
                f"{prefix}API_KEY", "AFRICAS_TALKING_API_KEY", env
            ),
            "username": _required_env_with_fallback(
                f"{prefix}USERNAME", "AFRICAS_TALKING_USERNAME", env
            ),
            "default_sender_id": _optional_env_with_fallback(
                f"{prefix}SENDER_ID", "AFRICAS_TALKING_SENDER_ID", env
            ),
            "base_url": base_url
            or _optional_env_with_fallback(f"{prefix}BASE_URL", "AFRICAS_TALKING_BASE_URL", env),
            "timeout_seconds": timeout_seconds
            if timeout_seconds is not None
            else get_env_number(f"{prefix}TIMEOUT_SECONDS", env),
            "default_headers": default_headers,
            "retry": retry,
            "hooks": hooks,
        }


class AfricasTalkingSmsClient(_AfricasTalkingSmsClientBase):
    """Synchronous Africa's Talking SMS client."""

    def __init__(self, *, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = HttpClient(client=client, **self._http_options)

    @classmethod
    def from_env(
        cls,
        *,
        client: Any = None,
        prefix: str = "AFRICASTALKING_",
        env: EnvLike | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> AfricasTalkingSmsClient:
        return cls(
            client=client,
            **cls._from_env_kwargs(
                prefix=prefix,
                env=env,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                default_headers=default_headers,
                retry=retry,
                hooks=hooks,
            )
        )

    def _request(
        self,
        path: str,
        method: str,
        *,
        form: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,  # type: ignore[arg-type]
                form=form,
                query=query,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _validate_response(self.provider_name, response)

    def send(self, request: SmsSendRequest, options: RequestOptions | None = None) -> SmsSendResult:
        _validate_send_request(request)

        receipts: list[SmsSendReceipt] = []
        raw_responses: list[Any] = []

        for group in _group_messages_by_text(request.messages):
            response = self._request(
                "/messaging", "POST", form=self._build_send_payload(request, group), options=options
            )
            raw_responses.append(response)
            receipts.extend(_build_send_receipts(self.provider_name, group, response))

        return _send_result(self.provider_name, receipts, raw_responses)

    def get_balance(self, options: RequestOptions | None = None) -> SmsBalance:
        response = self._request("/user", "GET", query={"username": self.username}, options=options)
        return _balance(self.provider_name, response)

    def send_premium(
        self, request: AfricasTalkingPremiumSmsRequest, options: RequestOptions | None = None
    ) -> SmsSendResult:
        response = self._request(
            "/messaging/premium", "POST", form=self._build_premium_payload(request), options=options
        )
        message = SmsMessage(
            recipient=request.recipient, text=request.text, metadata=request.metadata
        )
        receipts = _build_send_receipts(self.provider_name, [message], response)
        return _send_result(self.provider_name, receipts, response)

    def fetch_messages(
        self,
        request: AfricasTalkingFetchMessagesRequest | None = None,
        options: RequestOptions | None = None,
    ) -> AfricasTalkingFetchMessagesResult:
        request = request or AfricasTalkingFetchMessagesRequest()
        response = self._request(
            "/messaging", "GET", query=self._fetch_messages_query(request), options=options
        )
        return AfricasTalkingFetchMessagesResult(
            provider=self.provider_name,
            messages=_build_incoming_messages(self.provider_name, response),
            raw=response,
        )

    def create_subscription(
        self, request: AfricasTalkingSubscriptionRequest, options: RequestOptions | None = None
    ) -> AfricasTalkingSubscriptionResult:
        response = self._request(
            "/subscription/create", "POST",
            form=self._build_subscription_payload(request), options=options,
        )
        return _build_subscription_result(self.provider_name, response)

    def delete_subscription(
        self, request: AfricasTalkingSubscriptionRequest, options: RequestOptions | None = None
    ) -> AfricasTalkingSubscriptionResult:
        response = self._request(
            "/subscription/delete", "POST",
            form=self._build_subscription_payload(request), options=options,
        )
        return _build_subscription_result(self.provider_name, response)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AfricasTalkingSmsClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class AsyncAfricasTalkingSmsClient(_AfricasTalkingSmsClientBase):
    """Asynchronous Africa's Talking SMS client."""

    def __init__(self, *, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = AsyncHttpClient(client=client, **self._http_options)

    @classmethod
    def from_env(
        cls,
        *,
        client: Any = None,
        prefix: str = "AFRICASTALKING_",
        env: EnvLike | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> AsyncAfricasTalkingSmsClient:
        return cls(
            client=client,
            **cls._from_env_kwargs(
                prefix=prefix,
                env=env,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                default_headers=default_headers,
                retry=retry,
                hooks=hooks,
            )
        )

    async def _request(
        self,
        path: str,
        method: str,
        *,
        form: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = await self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,  # type: ignore[arg-type]
                form=form,
                query=query,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _validate_response(self.provider_name, response)

    async def send(
        self, request: SmsSendRequest, options: RequestOptions | None = None
    ) -> SmsSendResult:
        _validate_send_request(request)

        receipts: list[SmsSendReceipt] = []
        raw_responses: list[Any] = []

        for group in _group_messages_by_text(request.messages):
            response = await self._request(
                "/messaging", "POST", form=self._build_send_payload(request, group), options=options
            )
            raw_responses.append(response)
            receipts.extend(_build_send_receipts(self.provider_name, group, response))

        return _send_result(self.provider_name, receipts, raw_responses)

    async def get_balance(self, options: RequestOptions | None = None) -> SmsBalance:
        response = await self._request(
            "/user", "GET", query={"username": self.username}, options=options
        )
        return _balance(self.provider_name, response)

    async def send_premium(
        self, request: AfricasTalkingPremiumSmsRequest, options: RequestOptions | None = None
    ) -> SmsSendResult:
        response = await self._request(
            "/messaging/premium", "POST", form=self._build_premium_payload(request), options=options
        )
        message = SmsMessage(
            recipient=request.recipient, text=request.text, metadata=request.metadata
        )
        receipts = _build_send_receipts(self.provider_name, [message], response)
        return _send_result(self.provider_name, receipts, response)

    async def fetch_messages(
        self,
        request: AfricasTalkingFetchMessagesRequest | None = None,
        options: RequestOptions | None = None,
    ) -> AfricasTalkingFetchMessagesResult:
        request = request or AfricasTalkingFetchMessagesRequest()
        response = await self._request(
            "/messaging", "GET", query=self._fetch_messages_query(request), options=options
        )
        return AfricasTalkingFetchMessagesResult(
            provider=self.provider_name,
            messages=_build_incoming_messages(self.provider_name, response),
            raw=response,
        )

    async def create_subscription(
        self, request: AfricasTalkingSubscriptionRequest, options: RequestOptions | None = None
    ) -> AfricasTalkingSubscriptionResult:
        response = await self._request(
            "/subscription/create", "POST",
            form=self._build_subscription_payload(request), options=options,
        )
        return _build_subscription_result(self.provider_name, response)

    async def delete_subscription(
        self, request: AfricasTalkingSubscriptionRequest, options: RequestOptions | None = None
    ) -> AfricasTalkingSubscriptionResult:
        response = await self._request(
            "/subscription/delete", "POST",
            form=self._build_subscription_payload(request), options=options,
        )
        return _build_subscription_result(self.provider_name, response)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncAfricasTalkingSmsClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- #
# Shared parsing/validation helpers
# --------------------------------------------------------------------------- #


def parse_africastalking_delivery_report(
    payload: Mapping[str, Any],
) -> AfricasTalkingDeliveryReport:
    normalized = _normalize_mapping(payload)

    return AfricasTalkingDeliveryReport(
        id=first_text(
            normalized.get("id"), normalized.get("messageId"), normalized.get("message_id")
        ),
        phone_number=first_text(
            normalized.get("phoneNumber"), normalized.get("phone_number"), normalized.get("to")
        ),
        status=first_text(normalized.get("status"), normalized.get("Status")),
        failure_reason=first_text(
            normalized.get("failureReason"), normalized.get("failure_reason")
        ),
        network_code=first_text(
            normalized.get("networkCode"), normalized.get("network_code")
        ),
        retry_count=coerce_int(
            normalized.get("retryCount") if normalized.get("retryCount") is not None
            else normalized.get("retry_count")
        ),
        raw=normalized,
    )


def _send_result(
    provider_name: str, receipts: list[SmsSendReceipt], raw: Any
) -> SmsSendResult:
    raw_value = (raw[0] if len(raw) == 1 else raw) if isinstance(raw, list) else raw

    return SmsSendResult(
        provider=provider_name,
        accepted=any(receipt.status == "submitted" for receipt in receipts),
        messages=receipts,
        submitted_count=sum(1 for receipt in receipts if receipt.status == "submitted"),
        failed_count=sum(1 for receipt in receipts if receipt.status == "failed"),
        raw=raw_value,
    )


def _balance(provider_name: str, response: Mapping[str, Any]) -> SmsBalance:
    user_data = to_object(response.get("UserData"))
    balance_raw = coerce_string(user_data.get("balance"))

    return SmsBalance(
        provider=provider_name,
        entries=[
            SmsBalanceEntry(
                label="SMS",
                credits_raw=balance_raw,
                credits=parse_number_from_text(balance_raw),
                raw=user_data,
            )
        ],
        raw=response,
    )


def _validate_send_request(request: SmsSendRequest) -> None:
    if not request.messages:
        raise ValueError("SmsSendRequest.messages must not be empty.")

    for index, message in enumerate(request.messages):
        if coerce_string(message.recipient) is None:
            raise ValueError(f"messages[{index}].recipient must not be empty.")
        if coerce_string(message.text) is None:
            raise ValueError(f"messages[{index}].text must not be empty.")


def _group_messages_by_text(messages: list[SmsMessage]) -> list[list[SmsMessage]]:
    groups: dict[str, list[SmsMessage]] = {}
    order: list[str] = []

    for message in messages:
        key = message.text
        if key in groups:
            groups[key].append(message)
        else:
            groups[key] = [message]
            order.append(key)

    return [groups[key] for key in order]


def _build_send_receipts(
    provider_name: str, messages: list[SmsMessage], response: Mapping[str, Any]
) -> list[SmsSendReceipt]:
    data = to_object(response.get("SMSMessageData"))
    recipients = _normalize_rows(data.get("Recipients"))
    message_by_recipient = {message.recipient: message for message in messages}

    receipts: list[SmsSendReceipt] = []
    for index, row in enumerate(recipients):
        recipient = (
            coerce_string(row.get("number"))
            or (messages[index].recipient if index < len(messages) else "")
        )
        message = message_by_recipient.get(recipient) or (
            messages[index] if index < len(messages) else None
        )
        provider_message_id = coerce_string(row.get("messageId"))
        provider_status = coerce_string(row.get("status"))
        provider_error_code = coerce_string(row.get("statusCode"))
        submitted = _is_submitted_status(row.get("statusCode"), provider_status)

        receipts.append(
            SmsSendReceipt(
                provider=provider_name,
                recipient=recipient,
                text=message.text if message else "",
                status="submitted" if submitted else "failed",
                provider_message_id=provider_message_id,
                reference=message.reference if message else None,
                provider_error_code=None if submitted else provider_error_code,
                provider_error_description=None if submitted else provider_status,
                raw=row,
            )
        )

    return receipts


def _validate_response(provider_name: str, response: object) -> dict[str, Any]:
    payload = to_object(response)
    if not payload:
        raise ProviderError(
            "Africa's Talking returned a non-object response.",
            provider=provider_name,
            response_body=response,
        )

    if (
        "SMSMessageData" in payload
        or "UserData" in payload
        or "status" in payload
        or "description" in payload
    ):
        return payload

    raise ProviderError(
        "Africa's Talking returned an unexpected response shape.",
        provider=provider_name,
        response_body=payload,
    )


def _build_incoming_messages(
    provider_name: str, response: Mapping[str, Any]
) -> list[AfricasTalkingIncomingMessage]:
    data = to_object(response.get("SMSMessageData"))
    rows = _normalize_rows(data.get("Messages"))

    return [
        AfricasTalkingIncomingMessage(
            provider=provider_name,
            provider_message_id=coerce_string(row.get("id")),
            sender=first_text(row.get("from"), row.get("sender")),
            recipient=coerce_string(row.get("to")),
            text=first_text(row.get("text"), row.get("message")),
            link_id=coerce_string(row.get("linkId")),
            date=first_text(row.get("date"), row.get("dateReceived")),
            network_code=coerce_string(row.get("networkCode")),
            raw=row,
        )
        for row in rows
    ]


def _build_subscription_result(
    provider_name: str, response: Mapping[str, Any]
) -> AfricasTalkingSubscriptionResult:
    status = coerce_string(response.get("status"))
    description = first_text(response.get("description"), response.get("message"))

    return AfricasTalkingSubscriptionResult(
        provider=provider_name,
        success=status.lower() == "success" if status else True,
        description=description,
        raw=response,
    )


def _apply_provider_options(
    params: dict[str, str], provider_options: Mapping[str, Any] | None
) -> None:
    for key, value in (provider_options or {}).items():
        if value is not None:
            params[key] = value if isinstance(value, str) else _stringify(value)


def _normalize_query_options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for key, value in (options or {}).items():
        if value is None or isinstance(value, (str, int, float, bool)):
            query[key] = value
        else:
            query[key] = _stringify(value)
    return query


def _stringify(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _is_submitted_status(status_code: object, status: str | None) -> bool:
    code = coerce_int(status_code)
    if code is not None:
        return 100 <= code < 200

    normalized = (status or "").lower()
    return any(entry in normalized for entry in ("success", "sent", "submitted", "queued"))


def _map_delivery_state(status: str | None) -> Any:
    normalized = (status or "").lower()

    if normalized in ("sent", "submitted"):
        return "submitted"

    if normalized in ("success", "delivered"):
        return "delivered"

    if normalized in ("queued", "failed"):
        return normalized

    return "unknown"


def _normalize_rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    return []


def _normalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, entry in value.items():
        if isinstance(entry, (list, tuple)):
            normalized[key] = entry[0] if entry else None
        else:
            normalized[key] = entry
    return normalized


def _required_env_with_fallback(
    primary_name: str, fallback_name: str, env: EnvLike | None
) -> str:
    return get_optional_env(primary_name, env) or get_required_env(fallback_name, env)


def _optional_env_with_fallback(
    primary_name: str, fallback_name: str, env: EnvLike | None
) -> str | None:
    return get_optional_env(primary_name, env) or get_optional_env(fallback_name, env)
