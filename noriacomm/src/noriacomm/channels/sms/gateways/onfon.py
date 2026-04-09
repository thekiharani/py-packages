from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from ....events import DeliveryEvent
from ....exceptions import ConfigurationError, GatewayError
from ....http import AsyncHttpClient, HttpClient
from ....types import Hooks, HttpRequestOptions, RequestOptions, RetryPolicy
from ....utils import (
    coerce_string,
    first_text,
    format_schedule_time,
    merge_headers,
    normalize_query_mapping,
    parse_decimal_from_text,
    to_object,
)
from ..models import (
    SmsBalance,
    SmsBalanceEntry,
    SmsGroup,
    SmsGroupUpsertRequest,
    SmsManagementResult,
    SmsSendReceipt,
    SmsSendRequest,
    SmsSendResult,
    SmsTemplate,
    SmsTemplateUpsertRequest,
)

ONFON_SMS_BASE_URL = "https://api.onfonmedia.co.ke/v1/sms"
ONFON_BASE_URL = ONFON_SMS_BASE_URL


@dataclass(slots=True)
class OnfonSmsGateway:
    access_key: str
    api_key: str
    client_id: str
    default_sender_id: str | None = None
    base_url: str = ONFON_SMS_BASE_URL
    client: httpx.Client | Any | None = None
    async_client: httpx.AsyncClient | Any | None = None
    timeout_seconds: float | None = 30.0
    default_headers: Mapping[str, str] | None = None
    retry: RetryPolicy | None = None
    hooks: Hooks | None = None
    provider_name: str = field(init=False, default="onfon")
    _transport_headers: dict[str, str] = field(init=False, repr=False)
    _http: HttpClient | None = field(init=False, repr=False, default=None)
    _async_http: AsyncHttpClient | None = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self.access_key = _require_text(self.access_key, "access_key")
        self.api_key = _require_text(self.api_key, "api_key")
        self.client_id = _require_text(self.client_id, "client_id")
        self.default_sender_id = coerce_string(self.default_sender_id)
        self._transport_headers = merge_headers(
            self.default_headers,
            {
                "AccessKey": self.access_key,
                "Content-Type": "application/json",
            },
        )

    def send(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult:
        payload = self._build_send_payload(request)
        response = self._request(
            HttpRequestOptions(
                path="/SendBulkSMS",
                method="POST",
                body=payload,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_send_result(request, response)

    async def asend(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult:
        payload = self._build_send_payload(request)
        response = await self._arequest(
            HttpRequestOptions(
                path="/SendBulkSMS",
                method="POST",
                body=payload,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_send_result(request, response)

    def get_balance(self, *, options: RequestOptions | None = None) -> SmsBalance:
        response = self._request(
            HttpRequestOptions(
                path="/Balance",
                method="GET",
                query=self._auth_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_balance_result(response)

    async def aget_balance(self, *, options: RequestOptions | None = None) -> SmsBalance:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Balance",
                method="GET",
                query=self._auth_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_balance_result(response)

    def list_groups(self, *, options: RequestOptions | None = None) -> tuple[SmsGroup, ...]:
        response = self._request(
            HttpRequestOptions(
                path="/Group",
                method="GET",
                query=self._auth_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_group_list(response)

    async def alist_groups(self, *, options: RequestOptions | None = None) -> tuple[SmsGroup, ...]:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Group",
                method="GET",
                query=self._auth_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_group_list(response)

    def create_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = self._request(
            HttpRequestOptions(
                path="/Group",
                method="POST",
                body=self._build_group_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response)

    async def acreate_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Group",
                method="POST",
                body=self._build_group_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response)

    def update_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = self._request(
            HttpRequestOptions(
                path="/Group",
                method="PUT",
                query={"id": _require_identifier(group_id, "group_id")},
                body=self._build_group_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=group_id)

    async def aupdate_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Group",
                method="PUT",
                query={"id": _require_identifier(group_id, "group_id")},
                body=self._build_group_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=group_id)

    def delete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        group_id = _require_identifier(group_id, "group_id")
        response = self._request(
            HttpRequestOptions(
                path="/Group",
                method="DELETE",
                query={**self._auth_query(), "id": group_id},
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=group_id)

    async def adelete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        group_id = _require_identifier(group_id, "group_id")
        response = await self._arequest(
            HttpRequestOptions(
                path="/Group",
                method="DELETE",
                query={**self._auth_query(), "id": group_id},
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=group_id)

    def list_templates(self, *, options: RequestOptions | None = None) -> tuple[SmsTemplate, ...]:
        response = self._request(
            HttpRequestOptions(
                path="/Template",
                method="GET",
                query=self._auth_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_template_list(response)

    async def alist_templates(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsTemplate, ...]:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Template",
                method="GET",
                query=self._auth_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_template_list(response)

    def create_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = self._request(
            HttpRequestOptions(
                path="/Template",
                method="POST",
                body=self._build_template_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response)

    async def acreate_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Template",
                method="POST",
                body=self._build_template_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response)

    def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = self._request(
            HttpRequestOptions(
                path="/Template",
                method="PUT",
                query={"id": _require_identifier(template_id, "template_id")},
                body=self._build_template_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=template_id)

    async def aupdate_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        response = await self._arequest(
            HttpRequestOptions(
                path="/Template",
                method="PUT",
                query={"id": _require_identifier(template_id, "template_id")},
                body=self._build_template_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=template_id)

    def delete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        template_id = _require_identifier(template_id, "template_id")
        response = self._request(
            HttpRequestOptions(
                path="/Template",
                method="DELETE",
                query={**self._auth_query(), "id": template_id},
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=template_id)

    async def adelete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        template_id = _require_identifier(template_id, "template_id")
        response = await self._arequest(
            HttpRequestOptions(
                path="/Template",
                method="DELETE",
                query={**self._auth_query(), "id": template_id},
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_management_result(response, resource_id=template_id)

    def parse_delivery_report(self, payload: Mapping[str, object]) -> DeliveryEvent | None:
        normalized = normalize_query_mapping(payload)
        provider_message_id = first_text(normalized.get("messageId"), normalized.get("MessageId"))
        if provider_message_id is None:
            return None
        provider_status = first_text(normalized.get("status"), normalized.get("Status"))

        return DeliveryEvent(
            channel="sms",
            provider=self.provider_name,
            provider_message_id=provider_message_id,
            recipient=first_text(normalized.get("mobile"), normalized.get("MobileNumber")),
            state=_map_delivery_state(provider_status),
            provider_status=provider_status,
            error_code=first_text(normalized.get("errorCode"), normalized.get("ErrorCode")),
            occurred_at=first_text(
                normalized.get("doneDate"),
                normalized.get("DoneDate"),
                normalized.get("submitDate"),
                normalized.get("SubmitDate"),
            ),
            raw=normalized,
        )

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    async def aclose(self) -> None:
        if self._async_http is not None:
            await self._async_http.aclose()

    def _build_send_payload(self, request: SmsSendRequest) -> dict[str, Any]:
        _validate_send_request(request)
        sender_id = first_text(request.sender_id, self.default_sender_id)
        if sender_id is None:
            raise ConfigurationError(
                "sender_id is required either on SmsSendRequest or as default_sender_id."
            )

        payload = dict(request.provider_options or {})
        payload.update(
            {
                "SenderId": sender_id,
                "MessageParameters": [
                    {
                        "Number": message.recipient,
                        "Text": message.text,
                    }
                    for message in request.messages
                ],
                "ApiKey": self.api_key,
                "ClientId": self.client_id,
            }
        )

        if request.is_unicode is not None:
            payload["IsUnicode"] = request.is_unicode
        if request.is_flash is not None:
            payload["IsFlash"] = request.is_flash
        if request.schedule_at is not None:
            payload["ScheduleDateTime"] = format_schedule_time(request.schedule_at)

        return payload

    def _build_send_result(
        self,
        request: SmsSendRequest,
        response: Mapping[str, object],
    ) -> SmsSendResult:
        rows = response.get("Data")
        items = rows if isinstance(rows, list) else []
        receipts: list[SmsSendReceipt] = []

        for index, message in enumerate(request.messages):
            row = to_object(items[index]) if index < len(items) else {}
            provider_message_id = coerce_string(row.get("MessageId"))
            recipient = first_text(row.get("MobileNumber"), message.recipient) or message.recipient

            if provider_message_id is None:
                status = "failed"
                provider_error_code = "MISSING_MESSAGE_ID"
                provider_error_description = (
                    "Provider accepted the request but did not return "
                    "a MessageId for this recipient."
                )
            else:
                status = "submitted"
                provider_error_code = None
                provider_error_description = None

            receipts.append(
                SmsSendReceipt(
                    provider=self.provider_name,
                    recipient=recipient,
                    text=message.text,
                    status=status,
                    provider_message_id=provider_message_id,
                    reference=message.reference,
                    provider_error_code=provider_error_code,
                    provider_error_description=provider_error_description,
                    raw=row or None,
                )
            )

        return SmsSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=_normalize_error_code(response.get("ErrorCode")),
            error_description=coerce_string(response.get("ErrorDescription")),
            messages=tuple(receipts),
            raw=response,
        )

    def _build_balance_result(self, response: Mapping[str, object]) -> SmsBalance:
        rows = response.get("Data")
        items = rows if isinstance(rows, list) else []
        entries = tuple(
            SmsBalanceEntry(
                label=coerce_string(item.get("PluginType")),
                credits_raw=coerce_string(item.get("Credits")),
                credits=parse_decimal_from_text(coerce_string(item.get("Credits"))),
                raw=item,
            )
            for item in (to_object(row) for row in items)
        )
        return SmsBalance(provider=self.provider_name, entries=entries, raw=response)

    def _build_group_payload(self, request: SmsGroupUpsertRequest) -> dict[str, Any]:
        name = _require_text(request.name, "name")
        payload = dict(request.provider_options or {})
        payload.update(
            {
                "GroupName": name,
                "ApiKey": self.api_key,
                "ClientId": self.client_id,
            }
        )
        return payload

    def _build_template_payload(self, request: SmsTemplateUpsertRequest) -> dict[str, Any]:
        name = _require_text(request.name, "name")
        body = _require_text(request.body, "body")
        payload = dict(request.provider_options or {})
        payload.update(
            {
                "TemplateName": name,
                "MessageTemplate": body,
                "ApiKey": self.api_key,
                "ClientId": self.client_id,
            }
        )
        return payload

    def _build_group_list(self, response: Mapping[str, object]) -> tuple[SmsGroup, ...]:
        rows = response.get("Data")
        items = rows if isinstance(rows, list) else []
        return tuple(
            SmsGroup(
                group_id=_coerce_identifier(item.get("GroupId")) or "",
                name=coerce_string(item.get("GroupName")) or "",
                contact_count=_coerce_int(item.get("ContactCount")),
                raw=item,
            )
            for item in (to_object(row) for row in items)
            if _coerce_identifier(item.get("GroupId")) is not None
        )

    def _build_template_list(self, response: Mapping[str, object]) -> tuple[SmsTemplate, ...]:
        rows = response.get("Data")
        items = rows if isinstance(rows, list) else []
        return tuple(
            SmsTemplate(
                template_id=_coerce_identifier(item.get("TemplateId")) or "",
                name=coerce_string(item.get("TemplateName")) or "",
                body=coerce_string(item.get("MessageTemplate")) or "",
                approved=_coerce_bool(item.get("IsApproved")),
                active=_coerce_bool(item.get("IsActive")),
                created_at=coerce_string(item.get("CreatededDate")),
                approved_at=coerce_string(item.get("ApprovedDate")),
                raw=item,
            )
            for item in (to_object(row) for row in items)
            if _coerce_identifier(item.get("TemplateId")) is not None
        )

    def _build_management_result(
        self,
        response: Mapping[str, object],
        *,
        resource_id: str | None = None,
    ) -> SmsManagementResult:
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            message=(
                coerce_string(response.get("Data"))
                or coerce_string(response.get("ErrorDescription"))
            ),
            resource_id=_coerce_identifier(resource_id),
            raw=response,
        )

    def _request(self, options: HttpRequestOptions) -> dict[str, Any]:
        response = self._get_http().request(options)
        return self._validate_response(response)

    async def _arequest(self, options: HttpRequestOptions) -> dict[str, Any]:
        response = await self._get_async_http().request(options)
        return self._validate_response(response)

    def _get_http(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient(
                base_url=self.base_url,
                client=self.client,
                timeout_seconds=self.timeout_seconds,
                default_headers=self._transport_headers,
                retry=self.retry,
                hooks=self.hooks,
            )
        return self._http

    def _get_async_http(self) -> AsyncHttpClient:
        if self._async_http is None:
            self._async_http = AsyncHttpClient(
                base_url=self.base_url,
                client=self.async_client,
                timeout_seconds=self.timeout_seconds,
                default_headers=self._transport_headers,
                retry=self.retry,
                hooks=self.hooks,
            )
        return self._async_http

    def _validate_response(self, response: object) -> dict[str, Any]:
        payload = to_object(response)
        if not payload:
            raise GatewayError(
                "Onfon returned a non-object response.",
                provider=self.provider_name,
                response_body=response,
            )

        if not _is_success_payload(payload):
            error_code = _normalize_error_code(payload.get("ErrorCode"))
            error_description = (
                coerce_string(payload.get("ErrorDescription")) or "Provider request failed."
            )
            raise GatewayError(
                f"Onfon request failed: {error_description}",
                provider=self.provider_name,
                error_code=error_code,
                error_description=error_description,
                response_body=payload,
            )

        return payload

    def _auth_query(self) -> dict[str, str]:
        return {
            "ApiKey": self.api_key,
            "ClientId": self.client_id,
        }


def _validate_send_request(request: SmsSendRequest) -> None:
    if not request.messages:
        raise ValueError("SmsSendRequest.messages must not be empty.")

    for index, message in enumerate(request.messages):
        if coerce_string(message.recipient) is None:
            raise ValueError(f"messages[{index}].recipient must not be empty.")
        if coerce_string(message.text) is None:
            raise ValueError(f"messages[{index}].text must not be empty.")


def _require_text(value: str | None, field_name: str) -> str:
    text = coerce_string(value)
    if text is None:
        raise ConfigurationError(f"{field_name} is required.")
    return text


def _require_identifier(value: str | None, field_name: str) -> str:
    text = coerce_string(value)
    if text is None:
        raise ValueError(f"{field_name} is required.")
    return text


def _normalize_error_code(value: object) -> str | None:
    text = coerce_string(value)
    if text is None:
        return None
    if text.isdigit():
        return text.zfill(3)
    return text


def _coerce_identifier(value: object) -> str | None:
    return coerce_string(value)


def _coerce_int(value: object) -> int | None:
    text = coerce_string(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value

    text = coerce_string(value)
    if text is None:
        return None

    normalized = text.lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _is_success_payload(payload: Mapping[str, object]) -> bool:
    error_code = payload.get("ErrorCode")
    error_description = coerce_string(payload.get("ErrorDescription"))
    if not _is_success_code(error_code):
        return False
    if error_description is None:
        return True
    return "success" in error_description.lower()


def _is_success_code(value: object) -> bool:
    text = coerce_string(value)
    if text is None:
        return False
    try:
        return int(text) == 0
    except ValueError:
        return False


def _map_delivery_state(status: str | None) -> str:
    if status is None:
        return "unknown"

    normalized = status.upper()
    if normalized in {"DELIVRD", "DELIVERED"}:
        return "delivered"
    if normalized in {"ACCEPTD", "ACCEPTED", "SUBMITTED", "ENROUTE"}:
        return "submitted"
    if normalized in {"FAILED", "REJECTD", "UNDELIV", "EXPIRED"}:
        return "failed"
    return "unknown"


OnfonGateway = OnfonSmsGateway
