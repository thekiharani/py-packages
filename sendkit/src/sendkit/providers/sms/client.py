"""Onfon Media bulk SMS client (sync and async)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ...core.config import EnvLike, get_env_number, get_optional_env, get_required_env
from ...core.errors import ConfigurationError, ProviderError
from ...core.http import AsyncHttpClient, HttpClient
from ...core.types import HttpRequestOptions, RequestOptions
from ...core.utils import (
    coerce_boolean,
    coerce_int,
    coerce_string,
    first_text,
    format_schedule_time,
    parse_number_from_text,
    require_string,
    to_object,
)
from ...events import DeliveryEvent
from .types import (
    SmsBalance,
    SmsBalanceEntry,
    SmsGroup,
    SmsGroupUpsertRequest,
    SmsManagementResult,
    SmsMessage,
    SmsSendReceipt,
    SmsSendRequest,
    SmsSendResult,
    SmsTemplate,
    SmsTemplateUpsertRequest,
)

ONFON_SMS_BASE_URL = "https://api.onfonmedia.co.ke/v1/sms"
ONFON_BASE_URL = ONFON_SMS_BASE_URL


class _OnfonSmsClientBase:
    """Shared configuration, payload building, and response parsing for Onfon."""

    provider_name = "onfon"

    def __init__(
        self,
        *,
        access_key: str,
        api_key: str,
        client_id: str,
        default_sender_id: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> None:
        access_key = require_string(access_key, "access_key")
        self.api_key = require_string(api_key, "api_key")
        self.client_id = require_string(client_id, "client_id")
        self._default_sender_id = coerce_string(default_sender_id)
        self._http_options = {
            "base_url": base_url or ONFON_SMS_BASE_URL,
            "timeout_seconds": timeout_seconds if timeout_seconds is not None else 30.0,
            "default_headers": {
                "AccessKey": access_key,
                "Content-Type": "application/json",
                **(dict(default_headers) if default_headers else {}),
            },
            "retry": retry,
            "hooks": hooks,
        }

    # -- payload building (pure) -------------------------------------------- #

    def _auth_query(self) -> dict[str, str]:
        return {"ApiKey": self.api_key, "ClientId": self.client_id}

    def _build_send_payload(self, request: SmsSendRequest) -> dict[str, Any]:
        _validate_send_request(request)
        sender_id = first_text(request.sender_id, self._default_sender_id)

        if sender_id is None:
            raise ConfigurationError(
                "sender_id is required either on SmsSendRequest or as default_sender_id."
            )

        payload: dict[str, Any] = {
            **(dict(request.provider_options) if request.provider_options else {}),
            "SenderId": sender_id,
            "MessageParameters": [
                {"Number": message.recipient, "Text": message.text}
                for message in request.messages
            ],
            "ApiKey": self.api_key,
            "ClientId": self.client_id,
        }

        if request.is_unicode is not None:
            payload["IsUnicode"] = request.is_unicode

        if request.is_flash is not None:
            payload["IsFlash"] = request.is_flash

        if request.schedule_at is not None:
            payload["ScheduleDateTime"] = format_schedule_time(request.schedule_at)

        return payload

    def _build_send_result(
        self, request: SmsSendRequest, response: Mapping[str, Any]
    ) -> SmsSendResult:
        items = _normalize_rows(response.get("Data"))
        messages: list[SmsSendReceipt] = []
        for index, message in enumerate(request.messages):
            row = items[index] if index < len(items) else {}
            provider_message_id = coerce_string(row.get("MessageId"))
            recipient = first_text(row.get("MobileNumber"), message.recipient) or message.recipient
            messages.append(
                _build_send_receipt(
                    self.provider_name, message, row, recipient, provider_message_id
                )
            )

        return SmsSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=_normalize_error_code(response.get("ErrorCode")),
            error_description=coerce_string(response.get("ErrorDescription")),
            submitted_count=sum(1 for m in messages if m.status == "submitted"),
            failed_count=sum(1 for m in messages if m.status == "failed"),
            messages=messages,
            raw=response,
        )

    def parse_delivery_report(self, payload: Mapping[str, Any]) -> DeliveryEvent | None:
        normalized = _normalize_mapping(payload)
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
            metadata={},
            raw=normalized,
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
            "access_key": get_required_env(f"{prefix}ACCESS_KEY", env),
            "api_key": get_required_env(f"{prefix}API_KEY", env),
            "client_id": get_required_env(f"{prefix}CLIENT_ID", env),
            "default_sender_id": get_optional_env(f"{prefix}SENDER_ID", env),
            "base_url": base_url or get_optional_env(f"{prefix}BASE_URL", env),
            "timeout_seconds": timeout_seconds
            if timeout_seconds is not None
            else get_env_number(f"{prefix}TIMEOUT_SECONDS", env),
            "default_headers": default_headers,
            "retry": retry,
            "hooks": hooks,
        }


class OnfonSmsClient(_OnfonSmsClientBase):
    """Synchronous Onfon Media bulk SMS client."""

    def __init__(self, *, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = HttpClient(client=client, **self._http_options)

    @classmethod
    def from_env(
        cls,
        *,
        client: Any = None,
        prefix: str = "ONFON_",
        env: EnvLike | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> OnfonSmsClient:
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
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,  # type: ignore[arg-type]
                body=body,
                query=query,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _validate_response(self.provider_name, response)

    def send(self, request: SmsSendRequest, options: RequestOptions | None = None) -> SmsSendResult:
        response = self._request(
            "/SendBulkSMS", "POST", body=self._build_send_payload(request), options=options
        )
        return self._build_send_result(request, response)

    def get_balance(self, options: RequestOptions | None = None) -> SmsBalance:
        response = self._request("/Balance", "GET", query=self._auth_query(), options=options)
        return SmsBalance(
            provider=self.provider_name,
            entries=[_build_balance_entry(row) for row in _normalize_rows(response.get("Data"))],
            raw=response,
        )

    def list_groups(self, options: RequestOptions | None = None) -> list[SmsGroup]:
        response = self._request("/Group", "GET", query=self._auth_query(), options=options)
        return [
            group
            for group in (_build_group(row) for row in _normalize_rows(response.get("Data")))
            if group is not None
        ]

    def create_group(
        self, request: SmsGroupUpsertRequest, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        response = self._request(
            "/Group", "POST", body=_build_group_payload(request, self.api_key, self.client_id),
            options=options,
        )
        return _build_management_result(self.provider_name, response)

    def update_group(
        self, group_id: str, request: SmsGroupUpsertRequest, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        normalized_group_id = _require_identifier(group_id, "group_id")
        response = self._request(
            "/Group", "PUT", query={"id": normalized_group_id},
            body=_build_group_payload(request, self.api_key, self.client_id), options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_group_id)

    def delete_group(
        self, group_id: str, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        normalized_group_id = _require_identifier(group_id, "group_id")
        response = self._request(
            "/Group", "DELETE", query={**self._auth_query(), "id": normalized_group_id},
            options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_group_id)

    def list_templates(self, options: RequestOptions | None = None) -> list[SmsTemplate]:
        response = self._request("/Template", "GET", query=self._auth_query(), options=options)
        return [
            template
            for template in (_build_template(row) for row in _normalize_rows(response.get("Data")))
            if template is not None
        ]

    def create_template(
        self, request: SmsTemplateUpsertRequest, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        response = self._request(
            "/Template", "POST",
            body=_build_template_payload(request, self.api_key, self.client_id), options=options,
        )
        return _build_management_result(self.provider_name, response)

    def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        normalized_template_id = _require_identifier(template_id, "template_id")
        response = self._request(
            "/Template", "PUT", query={"id": normalized_template_id},
            body=_build_template_payload(request, self.api_key, self.client_id), options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_template_id)

    def delete_template(
        self, template_id: str, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        normalized_template_id = _require_identifier(template_id, "template_id")
        response = self._request(
            "/Template", "DELETE",
            query={**self._auth_query(), "id": normalized_template_id}, options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_template_id)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OnfonSmsClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class AsyncOnfonSmsClient(_OnfonSmsClientBase):
    """Asynchronous Onfon Media bulk SMS client."""

    def __init__(self, *, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = AsyncHttpClient(client=client, **self._http_options)

    @classmethod
    def from_env(
        cls,
        *,
        client: Any = None,
        prefix: str = "ONFON_",
        env: EnvLike | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_headers: Mapping[str, str] | None = None,
        retry: object = None,
        hooks: object = None,
    ) -> AsyncOnfonSmsClient:
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
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = await self._http.request(
            HttpRequestOptions(
                path=path,
                method=method,  # type: ignore[arg-type]
                body=body,
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
        response = await self._request(
            "/SendBulkSMS", "POST", body=self._build_send_payload(request), options=options
        )
        return self._build_send_result(request, response)

    async def get_balance(self, options: RequestOptions | None = None) -> SmsBalance:
        response = await self._request("/Balance", "GET", query=self._auth_query(), options=options)
        return SmsBalance(
            provider=self.provider_name,
            entries=[_build_balance_entry(row) for row in _normalize_rows(response.get("Data"))],
            raw=response,
        )

    async def list_groups(self, options: RequestOptions | None = None) -> list[SmsGroup]:
        response = await self._request("/Group", "GET", query=self._auth_query(), options=options)
        return [
            group
            for group in (_build_group(row) for row in _normalize_rows(response.get("Data")))
            if group is not None
        ]

    async def create_group(
        self, request: SmsGroupUpsertRequest, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        response = await self._request(
            "/Group", "POST", body=_build_group_payload(request, self.api_key, self.client_id),
            options=options,
        )
        return _build_management_result(self.provider_name, response)

    async def update_group(
        self, group_id: str, request: SmsGroupUpsertRequest, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        normalized_group_id = _require_identifier(group_id, "group_id")
        response = await self._request(
            "/Group", "PUT", query={"id": normalized_group_id},
            body=_build_group_payload(request, self.api_key, self.client_id), options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_group_id)

    async def delete_group(
        self, group_id: str, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        normalized_group_id = _require_identifier(group_id, "group_id")
        response = await self._request(
            "/Group", "DELETE", query={**self._auth_query(), "id": normalized_group_id},
            options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_group_id)

    async def list_templates(self, options: RequestOptions | None = None) -> list[SmsTemplate]:
        response = await self._request(
            "/Template", "GET", query=self._auth_query(), options=options
        )
        return [
            template
            for template in (_build_template(row) for row in _normalize_rows(response.get("Data")))
            if template is not None
        ]

    async def create_template(
        self, request: SmsTemplateUpsertRequest, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        response = await self._request(
            "/Template", "POST",
            body=_build_template_payload(request, self.api_key, self.client_id), options=options,
        )
        return _build_management_result(self.provider_name, response)

    async def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        normalized_template_id = _require_identifier(template_id, "template_id")
        response = await self._request(
            "/Template", "PUT", query={"id": normalized_template_id},
            body=_build_template_payload(request, self.api_key, self.client_id), options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_template_id)

    async def delete_template(
        self, template_id: str, options: RequestOptions | None = None
    ) -> SmsManagementResult:
        normalized_template_id = _require_identifier(template_id, "template_id")
        response = await self._request(
            "/Template", "DELETE",
            query={**self._auth_query(), "id": normalized_template_id}, options=options,
        )
        return _build_management_result(self.provider_name, response, normalized_template_id)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncOnfonSmsClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- #
# Shared parsing/validation helpers
# --------------------------------------------------------------------------- #


def _validate_send_request(request: SmsSendRequest) -> None:
    if not request.messages:
        raise ValueError("SmsSendRequest.messages must not be empty.")

    for index, message in enumerate(request.messages):
        if coerce_string(message.recipient) is None:
            raise ValueError(f"messages[{index}].recipient must not be empty.")
        if coerce_string(message.text) is None:
            raise ValueError(f"messages[{index}].text must not be empty.")


def _build_send_receipt(
    provider_name: str,
    message: SmsMessage,
    row: Mapping[str, Any],
    recipient: str,
    provider_message_id: str | None,
) -> SmsSendReceipt:
    if provider_message_id is None:
        return SmsSendReceipt(
            provider=provider_name,
            recipient=recipient,
            text=message.text,
            status="failed",
            reference=message.reference,
            provider_error_code="MISSING_MESSAGE_ID",
            provider_error_description=(
                "Provider accepted the request but did not return a MessageId for this recipient."
            ),
            raw=dict(row) if row else None,
        )

    return SmsSendReceipt(
        provider=provider_name,
        recipient=recipient,
        text=message.text,
        status="submitted",
        provider_message_id=provider_message_id,
        reference=message.reference,
        raw=dict(row) if row else None,
    )


def _build_balance_entry(row: Mapping[str, Any]) -> SmsBalanceEntry:
    credits_raw = coerce_string(row.get("Credits"))
    return SmsBalanceEntry(
        label=coerce_string(row.get("PluginType")),
        credits_raw=credits_raw,
        credits=parse_number_from_text(credits_raw),
        raw=row,
    )


def _build_group(row: Mapping[str, Any]) -> SmsGroup | None:
    group_id = coerce_string(row.get("GroupId"))
    if group_id is None:
        return None

    return SmsGroup(
        group_id=group_id,
        name=coerce_string(row.get("GroupName")) or "",
        contact_count=coerce_int(row.get("ContactCount")),
        raw=row,
    )


def _build_template(row: Mapping[str, Any]) -> SmsTemplate | None:
    template_id = coerce_string(row.get("TemplateId"))
    if template_id is None:
        return None

    return SmsTemplate(
        template_id=template_id,
        name=coerce_string(row.get("TemplateName")) or "",
        body=coerce_string(row.get("MessageTemplate")) or "",
        approved=coerce_boolean(row.get("IsApproved")),
        active=coerce_boolean(row.get("IsActive")),
        created_at=coerce_string(row.get("CreatededDate")),
        approved_at=coerce_string(row.get("ApprovedDate")),
        raw=row,
    )


def _build_group_payload(
    request: SmsGroupUpsertRequest, api_key: str, client_id: str
) -> dict[str, Any]:
    return {
        **(dict(request.provider_options) if request.provider_options else {}),
        "GroupName": require_string(request.name, "name"),
        "ApiKey": api_key,
        "ClientId": client_id,
    }


def _build_template_payload(
    request: SmsTemplateUpsertRequest, api_key: str, client_id: str
) -> dict[str, Any]:
    return {
        **(dict(request.provider_options) if request.provider_options else {}),
        "TemplateName": require_string(request.name, "name"),
        "MessageTemplate": require_string(request.body, "body"),
        "ApiKey": api_key,
        "ClientId": client_id,
    }


def _build_management_result(
    provider_name: str, response: Mapping[str, Any], resource_id: str | None = None
) -> SmsManagementResult:
    return SmsManagementResult(
        provider=provider_name,
        success=True,
        message=first_text(response.get("Data"), response.get("ErrorDescription")),
        resource_id=resource_id,
        raw=response,
    )


def _validate_response(provider_name: str, response: object) -> dict[str, Any]:
    payload = to_object(response)
    if not payload:
        raise ProviderError(
            "Onfon returned a non-object response.",
            provider=provider_name,
            response_body=response,
        )

    if not _is_success_payload(payload):
        error_code = _normalize_error_code(payload.get("ErrorCode"))
        error_description = (
            coerce_string(payload.get("ErrorDescription")) or "Provider request failed."
        )
        raise ProviderError(
            f"Onfon request failed: {error_description}",
            provider=provider_name,
            error_code=error_code,
            error_description=error_description,
            response_body=payload,
        )

    return payload


def _is_success_payload(payload: Mapping[str, Any]) -> bool:
    error_code = payload.get("ErrorCode")
    error_description = coerce_string(payload.get("ErrorDescription"))

    if not _is_success_code(error_code):
        return False

    if error_description is None:
        return True

    return "success" in error_description.lower()


def _is_success_code(value: object) -> bool:
    normalized = _normalize_error_code(value)
    return normalized is None or normalized in ("000", "0")


def _normalize_error_code(value: object) -> str | None:
    normalized = coerce_string(value)
    if not normalized:
        return None

    return normalized.zfill(3) if re.fullmatch(r"\d+", normalized) else normalized


def _map_delivery_state(status: str | None) -> Any:
    normalized = (status or "").lower()

    if normalized in ("accepted", "queued"):
        return normalized

    if normalized in ("sent", "submitted"):
        return "submitted"

    if normalized in ("delivered", "read", "failed"):
        return normalized

    return "unknown"


def _normalize_rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    return []


def _normalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, entry in value.items():
        normalized[key] = entry[0] if isinstance(entry, (list, tuple)) and entry else (
            None if isinstance(entry, (list, tuple)) else entry
        )
    return normalized


def _require_identifier(value: object, field_name: str) -> str:
    normalized = coerce_string(value)
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized
