from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import pytest

import noriacomm.channels.whatsapp.gateways.meta as meta_gateway_module
import noriacomm.http as http_module
from noriacomm.channels.sms.gateways.onfon import (
    OnfonSmsGateway,
    _coerce_bool,
    _coerce_int,
    _is_success_code,
    _is_success_payload,
    _map_delivery_state,
    _normalize_error_code,
    _validate_send_request,
)
from noriacomm.channels.sms.gateways.onfon import (
    _require_identifier as require_onfon_identifier,
)
from noriacomm.channels.sms.gateways.onfon import (
    _require_text as require_onfon_text,
)
from noriacomm.channels.sms.models import (
    SmsBalance,
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
from noriacomm.channels.sms.service import AsyncSmsService, SmsService
from noriacomm.channels.whatsapp.gateways.meta import (
    MetaWhatsAppGateway,
    _build_catalog_message_payload,
    _build_flow_message_payload,
    _build_managed_template,
    _build_media_delete_result,
    _build_media_info,
    _build_media_upload_files,
    _build_media_upload_form,
    _build_media_upload_result,
    _build_product_list_payload,
    _build_product_message_payload,
    _build_template_button_definition,
    _build_template_component,
    _build_template_component_definition,
    _build_template_create_payload,
    _build_template_delete_query,
    _build_template_delete_result,
    _build_template_fields_query,
    _build_template_list_query,
    _build_template_list_result,
    _build_template_mutation_result,
    _build_template_parameter,
    _build_template_payload,
    _build_template_update_payload,
    _build_text_payload,
    _first_mapping,
    _map_whatsapp_state,
)
from noriacomm.channels.whatsapp.gateways.meta import (
    _require_text as require_meta_text,
)
from noriacomm.channels.whatsapp.models import (
    WhatsAppCatalogMessageRequest,
    WhatsAppContact,
    WhatsAppContactAddress,
    WhatsAppContactEmail,
    WhatsAppContactName,
    WhatsAppContactOrg,
    WhatsAppContactPhone,
    WhatsAppContactsRequest,
    WhatsAppContactUrl,
    WhatsAppFlowMessageRequest,
    WhatsAppInboundMessage,
    WhatsAppInteractiveButton,
    WhatsAppInteractiveHeader,
    WhatsAppInteractiveRequest,
    WhatsAppInteractiveSection,
    WhatsAppLocationRequest,
    WhatsAppManagedTemplate,
    WhatsAppMediaDeleteResult,
    WhatsAppMediaInfo,
    WhatsAppMediaRequest,
    WhatsAppMediaUploadRequest,
    WhatsAppMediaUploadResult,
    WhatsAppProductItem,
    WhatsAppProductListRequest,
    WhatsAppProductMessageRequest,
    WhatsAppProductSection,
    WhatsAppReactionRequest,
    WhatsAppSendReceipt,
    WhatsAppSendResult,
    WhatsAppTemplateButtonDefinition,
    WhatsAppTemplateComponent,
    WhatsAppTemplateComponentDefinition,
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDeleteRequest,
    WhatsAppTemplateDeleteResult,
    WhatsAppTemplateListRequest,
    WhatsAppTemplateListResult,
    WhatsAppTemplateListSummary,
    WhatsAppTemplateMutationResult,
    WhatsAppTemplateParameter,
    WhatsAppTemplateRequest,
    WhatsAppTemplateUpdateRequest,
    WhatsAppTextRequest,
)
from noriacomm.channels.whatsapp.service import AsyncWhatsAppService, WhatsAppService
from noriacomm.client import AsyncMessagingClient, MessagingClient
from noriacomm.events import DeliveryEvent
from noriacomm.exceptions import (
    ApiError,
    ConfigurationError,
    GatewayError,
    NetworkError,
    TimeoutError,
    WebhookVerificationError,
)
from noriacomm.http import (
    AsyncHttpClient,
    HttpClient,
    _build_request_kwargs,
    _calculate_retry_delay,
    _normalize_hook_sequence,
    _resolve_retry_policy,
    _should_retry,
)
from noriacomm.types import (
    Hooks,
    HttpRequestOptions,
    RequestOptions,
    RetryDecisionContext,
    RetryPolicy,
)
from noriacomm.utils import (
    append_path,
    build_error_message,
    coerce_string,
    first_text,
    format_schedule_time,
    merge_headers,
    normalize_query_mapping,
    parse_decimal_from_text,
    parse_response_body,
)
from noriacomm.webhooks.fastapi import (
    fastapi_parse_meta_delivery_events,
    fastapi_parse_meta_inbound_messages,
    fastapi_parse_onfon_delivery_report,
    fastapi_resolve_meta_subscription_challenge,
)
from noriacomm.webhooks.flask import (
    flask_parse_meta_delivery_events,
    flask_parse_meta_inbound_messages,
    flask_parse_onfon_delivery_report,
    flask_resolve_meta_subscription_challenge,
)
from noriacomm.webhooks.meta import (
    require_valid_meta_signature,
    resolve_meta_subscription_challenge,
    verify_meta_signature,
)
from noriacomm.webhooks.onfon import parse_onfon_delivery_report


def make_response(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        headers={"content-type": "application/json"},
    )


@dataclass(slots=True)
class SequencedSyncRequester:
    actions: list[object]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.actions:
            raise AssertionError("No sync actions left.")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class SequencedAsyncRequester:
    actions: list[object]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def request(self, **kwargs: Any) -> httpx.Response:
        self.calls.append(kwargs)
        if not self.actions:
            raise AssertionError("No async actions left.")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    async def aclose(self) -> None:
        self.closed = True


@dataclass(slots=True)
class FakeFastAPIRequest:
    query_params: dict[str, object] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    payload: bytes = b"{}"

    async def body(self) -> bytes:
        return self.payload


@dataclass(slots=True)
class FakeFlaskRequest:
    args: dict[str, object] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    payload: bytes = b"{}"
    json_payload: object = None

    def get_data(self) -> bytes:
        return self.payload

    def get_json(self, silent: bool = True) -> object:
        return self.json_payload


@dataclass(slots=True)
class DummySmsGateway:
    provider_name: str = "dummy-sms"
    closed: bool = False
    calls: list[tuple[str, object]] = field(default_factory=list)

    def send(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult:
        self.calls.append(("send", options))
        return SmsSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                SmsSendReceipt(
                    provider=self.provider_name,
                    recipient=request.messages[0].recipient,
                    text=request.messages[0].text,
                    status="submitted",
                    provider_message_id="sms-1",
                ),
            ),
        )

    def get_balance(self, *, options: RequestOptions | None = None) -> SmsBalance:
        self.calls.append(("get_balance", options))
        return SmsBalance(provider=self.provider_name, entries=())

    def parse_delivery_report(self, payload: dict[str, object]) -> DeliveryEvent:
        self.calls.append(("parse_delivery_report", payload))
        return DeliveryEvent(
            channel="sms",
            provider=self.provider_name,
            provider_message_id="sms-1",
            state="delivered",
            recipient="254700000001",
        )

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class DummySmsManagementGateway(DummySmsGateway):
    def list_groups(self, *, options: RequestOptions | None = None) -> tuple[SmsGroup, ...]:
        self.calls.append(("list_groups", options))
        return (SmsGroup(group_id="1", name="Customers"),)

    def create_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("create_group", options))
        return SmsManagementResult(provider=self.provider_name, success=True, message=request.name)

    def update_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("update_group", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            message=request.name,
            resource_id=group_id,
        )

    def delete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("delete_group", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            resource_id=group_id,
        )

    def list_templates(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsTemplate, ...]:
        self.calls.append(("list_templates", options))
        return (SmsTemplate(template_id="1", name="welcome", body="Hello"),)

    def create_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("create_template", options))
        return SmsManagementResult(provider=self.provider_name, success=True, message=request.name)

    def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("update_template", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            message=request.name,
            resource_id=template_id,
        )

    def delete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("delete_template", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            resource_id=template_id,
        )


@dataclass(slots=True)
class DummyAsyncSmsGateway:
    provider_name: str = "dummy-sms"
    closed: bool = False
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def asend(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult:
        self.calls.append(("asend", options))
        return SmsSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                SmsSendReceipt(
                    provider=self.provider_name,
                    recipient=request.messages[0].recipient,
                    text=request.messages[0].text,
                    status="submitted",
                    provider_message_id="sms-async-1",
                ),
            ),
        )

    async def aget_balance(self, *, options: RequestOptions | None = None) -> SmsBalance:
        self.calls.append(("aget_balance", options))
        return SmsBalance(provider=self.provider_name, entries=())

    def parse_delivery_report(self, payload: dict[str, object]) -> DeliveryEvent:
        self.calls.append(("parse_delivery_report", payload))
        return DeliveryEvent(
            channel="sms",
            provider=self.provider_name,
            provider_message_id="sms-async-1",
            state="submitted",
            recipient="254700000002",
        )

    async def aclose(self) -> None:
        self.closed = True


@dataclass(slots=True)
class DummyAsyncSmsManagementGateway(DummyAsyncSmsGateway):
    async def alist_groups(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsGroup, ...]:
        self.calls.append(("alist_groups", options))
        return (SmsGroup(group_id="2", name="Leads"),)

    async def acreate_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("acreate_group", options))
        return SmsManagementResult(provider=self.provider_name, success=True, message=request.name)

    async def aupdate_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("aupdate_group", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            message=request.name,
            resource_id=group_id,
        )

    async def adelete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("adelete_group", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            resource_id=group_id,
        )

    async def alist_templates(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsTemplate, ...]:
        self.calls.append(("alist_templates", options))
        return (SmsTemplate(template_id="2", name="promo", body="Promo"),)

    async def acreate_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("acreate_template", options))
        return SmsManagementResult(provider=self.provider_name, success=True, message=request.name)

    async def aupdate_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("aupdate_template", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            message=request.name,
            resource_id=template_id,
        )

    async def adelete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        self.calls.append(("adelete_template", options))
        return SmsManagementResult(
            provider=self.provider_name,
            success=True,
            resource_id=template_id,
        )


@dataclass(slots=True)
class DummyWhatsAppGateway:
    provider_name: str = "dummy-wa"
    closed: bool = False
    calls: list[tuple[str, object]] = field(default_factory=list)

    def send_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_text", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-1",
                ),
            ),
        )

    def send_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_template", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="failed",
                    provider_message_id="wa-2",
                ),
            ),
        )

    def list_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        self.calls.append(("list_templates", (request, options)))
        return WhatsAppTemplateListResult(
            provider=self.provider_name,
            templates=(
                WhatsAppManagedTemplate(
                    provider=self.provider_name,
                    template_id="wa-template-1",
                    name="shipment_update",
                    language="en_US",
                    category="UTILITY",
                    status="APPROVED",
                    components=(
                        WhatsAppTemplateComponentDefinition(
                            type="BODY",
                            text="Hello {{1}}",
                        ),
                    ),
                ),
            ),
            summary=WhatsAppTemplateListSummary(total_count=1),
            after="wa-template-cursor-1",
        )

    def get_template(
        self,
        template_id: str,
        *,
        fields: tuple[str, ...] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        self.calls.append(("get_template", (template_id, fields, options)))
        return WhatsAppManagedTemplate(
            provider=self.provider_name,
            template_id=template_id,
            name="shipment_update",
            language="en_US",
            category="UTILITY",
            status="APPROVED",
            parameter_format="POSITIONAL",
        )

    def create_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        self.calls.append(("create_template", (request, options)))
        return WhatsAppTemplateMutationResult(
            provider=self.provider_name,
            success=True,
            template_id="wa-template-2",
            name=request.name,
            category=request.category.upper(),
            status="PENDING",
        )

    def update_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        self.calls.append(("update_template", (template_id, request, options)))
        return WhatsAppTemplateMutationResult(
            provider=self.provider_name,
            success=True,
            template_id=template_id,
            category=(request.category or "UTILITY").upper(),
            status="APPROVED",
        )

    def delete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult:
        self.calls.append(("delete_template", (request, options)))
        return WhatsAppTemplateDeleteResult(
            provider=self.provider_name,
            deleted=True,
            name=request.name,
            template_id=request.template_id,
            template_ids=tuple(request.template_ids),
        )

    def send_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_media", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-3",
                ),
            ),
        )

    def send_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_location", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-4",
                ),
            ),
        )

    def send_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_contacts", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-5",
                ),
            ),
        )

    def send_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_reaction", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-6",
                ),
            ),
        )

    def send_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_interactive", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-7",
                ),
            ),
        )

    def send_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_catalog", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-8",
                ),
            ),
        )

    def send_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_product", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-9",
                ),
            ),
        )

    def send_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_product_list", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-10",
                ),
            ),
        )

    def send_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("send_flow", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-11",
                ),
            ),
        )

    def upload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult:
        self.calls.append(("upload_media", options))
        return WhatsAppMediaUploadResult(
            provider=self.provider_name,
            media_id="media-upload-1",
        )

    def get_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo:
        self.calls.append(("get_media", options))
        return WhatsAppMediaInfo(provider=self.provider_name, media_id=media_id)

    def delete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult:
        self.calls.append(("delete_media", options))
        return WhatsAppMediaDeleteResult(
            provider=self.provider_name,
            media_id=media_id,
            deleted=True,
        )

    def parse_events(self, payload: dict[str, object]) -> tuple[DeliveryEvent, ...]:
        self.calls.append(("parse_events", payload))
        return (
            DeliveryEvent(
                channel="whatsapp",
                provider=self.provider_name,
                provider_message_id="wa-evt-1",
                state="read",
                recipient="254700000003",
            ),
        )

    def parse_event(self, payload: dict[str, object]) -> DeliveryEvent | None:
        events = self.parse_events(payload)
        return events[0] if events else None

    def parse_inbound_messages(
        self,
        payload: dict[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]:
        self.calls.append(("parse_inbound_messages", payload))
        return (
            WhatsAppInboundMessage(
                provider=self.provider_name,
                sender_id="254700000020",
                message_id="wamid.inbound",
                message_type="text",
                text="hello inbound",
            ),
        )

    def parse_inbound_message(self, payload: dict[str, object]) -> WhatsAppInboundMessage | None:
        messages = self.parse_inbound_messages(payload)
        return messages[0] if messages else None

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class DummyAsyncWhatsAppGateway:
    provider_name: str = "dummy-wa"
    closed: bool = False
    calls: list[tuple[str, object]] = field(default_factory=list)

    async def asend_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_text", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-1",
                ),
            ),
        )

    async def asend_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_template", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="failed",
                    provider_message_id="wa-async-2",
                ),
            ),
        )

    async def alist_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        self.calls.append(("alist_templates", (request, options)))
        return WhatsAppTemplateListResult(
            provider=self.provider_name,
            templates=(
                WhatsAppManagedTemplate(
                    provider=self.provider_name,
                    template_id="wa-template-async-1",
                    name="shipment_update_async",
                    language="en_US",
                    category="UTILITY",
                    status="APPROVED",
                ),
            ),
            summary=WhatsAppTemplateListSummary(total_count=1),
            after="wa-template-async-cursor-1",
        )

    async def aget_template(
        self,
        template_id: str,
        *,
        fields: tuple[str, ...] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        self.calls.append(("aget_template", (template_id, fields, options)))
        return WhatsAppManagedTemplate(
            provider=self.provider_name,
            template_id=template_id,
            name="shipment_update_async",
            language="en_US",
            category="UTILITY",
            status="APPROVED",
            parameter_format="POSITIONAL",
        )

    async def acreate_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        self.calls.append(("acreate_template", (request, options)))
        return WhatsAppTemplateMutationResult(
            provider=self.provider_name,
            success=True,
            template_id="wa-template-async-2",
            name=request.name,
            category=request.category.upper(),
            status="PENDING",
        )

    async def aupdate_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        self.calls.append(("aupdate_template", (template_id, request, options)))
        return WhatsAppTemplateMutationResult(
            provider=self.provider_name,
            success=True,
            template_id=template_id,
            category=(request.category or "UTILITY").upper(),
            status="APPROVED",
        )

    async def adelete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult:
        self.calls.append(("adelete_template", (request, options)))
        return WhatsAppTemplateDeleteResult(
            provider=self.provider_name,
            deleted=True,
            name=request.name,
            template_id=request.template_id,
            template_ids=tuple(request.template_ids),
        )

    async def asend_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_media", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-3",
                ),
            ),
        )

    async def asend_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_location", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-4",
                ),
            ),
        )

    async def asend_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_contacts", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-5",
                ),
            ),
        )

    async def asend_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_reaction", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-6",
                ),
            ),
        )

    async def asend_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_interactive", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-7",
                ),
            ),
        )

    async def asend_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_catalog", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-8",
                ),
            ),
        )

    async def asend_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_product", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-9",
                ),
            ),
        )

    async def asend_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_product_list", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-10",
                ),
            ),
        )

    async def asend_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        self.calls.append(("asend_flow", options))
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(
                WhatsAppSendReceipt(
                    provider=self.provider_name,
                    recipient=request.recipient,
                    status="submitted",
                    provider_message_id="wa-async-11",
                ),
            ),
        )

    async def aupload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult:
        self.calls.append(("aupload_media", options))
        return WhatsAppMediaUploadResult(
            provider=self.provider_name,
            media_id="media-upload-async-1",
        )

    async def aget_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo:
        self.calls.append(("aget_media", options))
        return WhatsAppMediaInfo(provider=self.provider_name, media_id=media_id)

    async def adelete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult:
        self.calls.append(("adelete_media", options))
        return WhatsAppMediaDeleteResult(
            provider=self.provider_name,
            media_id=media_id,
            deleted=True,
        )

    def parse_events(self, payload: dict[str, object]) -> tuple[DeliveryEvent, ...]:
        self.calls.append(("parse_events", payload))
        return (
            DeliveryEvent(
                channel="whatsapp",
                provider=self.provider_name,
                provider_message_id="wa-evt-async-1",
                state="delivered",
                recipient="254700000004",
            ),
        )

    def parse_event(self, payload: dict[str, object]) -> DeliveryEvent | None:
        events = self.parse_events(payload)
        return events[0] if events else None

    def parse_inbound_messages(
        self,
        payload: dict[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]:
        self.calls.append(("parse_inbound_messages", payload))
        return (
            WhatsAppInboundMessage(
                provider=self.provider_name,
                sender_id="254700000021",
                message_id="wamid.inbound.async",
                message_type="text",
                text="hello inbound async",
            ),
        )

    def parse_inbound_message(self, payload: dict[str, object]) -> WhatsAppInboundMessage | None:
        messages = self.parse_inbound_messages(payload)
        return messages[0] if messages else None

    async def aclose(self) -> None:
        self.closed = True


def test_utils_exceptions_and_signature_error_paths() -> None:
    assert append_path("https://api.example.com/", "https://override.example.com/items") == (
        "https://override.example.com/items"
    )
    assert coerce_string("  hello ") == "hello"
    assert coerce_string("   ") is None
    assert first_text(None, "  ", "value") == "value"
    assert format_schedule_time(" 2026-04-08 09:30 ") == "2026-04-08 09:30"
    with pytest.raises(ValueError, match="schedule_at must not be empty"):
        format_schedule_time(" ")
    assert parse_response_body(make_response(200, {"ok": True})) == {"ok": True}
    assert (
        parse_response_body(
            httpx.Response(204, text="", headers={"content-type": "text/plain"})
        )
        is None
    )
    assert parse_response_body(
        httpx.Response(200, text='{"message":"parsed"}', headers={"content-type": "text/plain"})
    ) == {"message": "parsed"}
    assert parse_response_body(
        httpx.Response(200, text="plain-text", headers={"content-type": "text/plain"})
    ) == "plain-text"
    assert build_error_message(400, {"ErrorDescription": "Bad request"}) == "Bad request"
    assert build_error_message(500, {}) == "Request failed with status 500"
    assert merge_headers(None, {"A": "1"}, {"A": "2", "B": "3"}) == {"A": "2", "B": "3"}
    assert parse_decimal_from_text("KES 1,234.50") == Decimal("1234.50")
    assert parse_decimal_from_text("nothing here") is None
    assert parse_decimal_from_text(None) is None
    assert normalize_query_mapping({"a": [" x "], "b": [], "c": 7}) == {
        "a": "x",
        "b": None,
        "c": "7",
    }

    configuration_error = ConfigurationError("bad config", details={"field": "token"})
    network_error = NetworkError("network issue", details={"retryable": True})
    timeout_error = TimeoutError("timeout")
    webhook_error = WebhookVerificationError("invalid webhook")
    assert configuration_error.code == "CONFIGURATION_ERROR"
    assert configuration_error.details == {"field": "token"}
    assert network_error.code == "NETWORK_ERROR"
    assert timeout_error.code == "TIMEOUT_ERROR"
    assert webhook_error.code == "WEBHOOK_VERIFICATION_ERROR"

    with pytest.raises(ConfigurationError, match="verify_token is required"):
        resolve_meta_subscription_challenge({}, "")
    assert resolve_meta_subscription_challenge({"hub.mode": "ping"}, "verify-me") is None
    assert (
        resolve_meta_subscription_challenge(
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "123",
            },
            "verify-me",
        )
        is None
    )

    with pytest.raises(ConfigurationError, match="app_secret is required"):
        verify_meta_signature(b"{}", "sha256=abc", "")
    assert verify_meta_signature(b"{}", None, "secret") is False
    assert verify_meta_signature(b"{}", "sha1=abc", "secret") is False
    with pytest.raises(WebhookVerificationError, match="signature verification failed"):
        require_valid_meta_signature(b"{}", "sha256=bad", "secret")


def test_http_helper_functions_cover_retry_resolution_and_request_building() -> None:
    def hook(context: Any) -> None:
        return None

    assert _normalize_hook_sequence(None) == []
    assert _normalize_hook_sequence(hook) == [hook]
    assert _normalize_hook_sequence([hook]) == [hook]

    default_retry = RetryPolicy(
        max_attempts=3,
        retry_methods=("GET",),
        retry_on_statuses=(500,),
        retry_on_network_error=True,
        base_delay_seconds=1.0,
        max_delay_seconds=5.0,
        backoff_multiplier=3.0,
        should_retry=lambda context: context.status != 429,
    )
    override_retry = RetryPolicy(
        max_attempts=2,
        retry_methods=(),
        retry_on_statuses=(),
        retry_on_network_error=False,
        base_delay_seconds=0.5,
        max_delay_seconds=1.0,
        backoff_multiplier=2.0,
    )

    assert _resolve_retry_policy(default_retry, False) is None
    assert _resolve_retry_policy(default_retry, True) is default_retry
    assert _resolve_retry_policy(default_retry, None) is default_retry
    assert _resolve_retry_policy(None, override_retry) is override_retry
    resolved = _resolve_retry_policy(default_retry, override_retry)
    assert resolved is not None
    assert resolved.max_attempts == 2
    assert resolved.retry_methods == ("GET",)
    assert resolved.retry_on_statuses == (500,)
    assert resolved.should_retry is default_retry.should_retry

    assert (
        _should_retry(
            None,
            RetryDecisionContext(attempt=1, max_attempts=2, method="GET", url="https://api.test"),
        )
        is False
    )
    assert (
        _should_retry(
            default_retry,
            RetryDecisionContext(attempt=2, max_attempts=2, method="GET", url="https://api.test"),
        )
        is False
    )
    assert (
        _should_retry(
            RetryPolicy(max_attempts=2, retry_methods=("POST",), retry_on_statuses=(500,)),
            RetryDecisionContext(
                attempt=1,
                max_attempts=2,
                method="GET",
                url="https://api.test",
                status=500,
            ),
        )
        is False
    )
    assert (
        _should_retry(
            RetryPolicy(max_attempts=2, retry_methods=("GET",), retry_on_statuses=(503,)),
            RetryDecisionContext(
                attempt=1,
                max_attempts=2,
                method="GET",
                url="https://api.test",
                status=500,
            ),
        )
        is False
    )
    assert (
        _should_retry(
            RetryPolicy(max_attempts=2, retry_methods=("GET",), retry_on_network_error=False),
            RetryDecisionContext(
                attempt=1,
                max_attempts=2,
                method="GET",
                url="https://api.test",
                error=RuntimeError("boom"),
            ),
        )
        is False
    )
    assert (
        _should_retry(
            RetryPolicy(
                max_attempts=2,
                retry_methods=("GET",),
                retry_on_statuses=(500,),
                should_retry=lambda context: False,
            ),
            RetryDecisionContext(
                attempt=1,
                max_attempts=2,
                method="GET",
                url="https://api.test",
                status=500,
            ),
        )
        is False
    )
    assert (
        _should_retry(
            RetryPolicy(max_attempts=2, retry_methods=("GET",), retry_on_statuses=(500,)),
            RetryDecisionContext(
                attempt=1,
                max_attempts=2,
                method="GET",
                url="https://api.test",
                status=500,
            ),
        )
        is True
    )
    assert _calculate_retry_delay(None, 1) == 0.0
    assert (
        _calculate_retry_delay(
            RetryPolicy(base_delay_seconds=2.0, max_delay_seconds=3.0, backoff_multiplier=4.0),
            2,
        )
        == 3.0
    )

    text_kwargs = _build_request_kwargs(
        method="POST",
        url="https://api.test/messages",
        headers={"X-Test": "1"},
        query={"page": 1, "skip": None},
        body="hello",
        form=None,
        files=None,
        timeout_seconds=5.0,
    )
    assert text_kwargs["params"] == {"page": 1}
    assert text_kwargs["content"] == "hello"
    assert text_kwargs["headers"]["Content-Type"] == "text/plain;charset=UTF-8"

    json_kwargs = _build_request_kwargs(
        method="POST",
        url="https://api.test/messages",
        headers={"X-Test": "1"},
        query=None,
        body={"message": "hello"},
        form=None,
        files=None,
        timeout_seconds=None,
    )
    assert json_kwargs["json"] == {"message": "hello"}
    assert json_kwargs["headers"]["Content-Type"] == "application/json"

    preserved_headers = _build_request_kwargs(
        method="POST",
        url="https://api.test/messages",
        headers={"content-type": "application/xml"},
        query=None,
        body=b"<xml />",
        form=None,
        files=None,
        timeout_seconds=None,
    )
    assert preserved_headers["headers"] == {"content-type": "application/xml"}

    multipart_kwargs = _build_request_kwargs(
        method="POST",
        url="https://api.test/media",
        headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
        query=None,
        body=None,
        form={"messaging_product": "whatsapp"},
        files={"file": ("poster.png", b"img", "image/png")},
        timeout_seconds=10.0,
    )
    assert multipart_kwargs["data"] == {"messaging_product": "whatsapp"}
    assert multipart_kwargs["files"]["file"] == ("poster.png", b"img", "image/png")
    assert multipart_kwargs["headers"] == {"Authorization": "Bearer token"}


def test_http_client_sync_paths_cover_retries_hooks_and_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("GET", "https://api.test/items")
    requester = SequencedSyncRequester(
        actions=[
            httpx.ReadTimeout("timed out", request=request),
            make_response(200, {"ok": True}),
        ]
    )
    before_attempts: list[int] = []
    after_statuses: list[int] = []
    error_types: list[str] = []
    sleep_calls: list[float] = []

    def before_hook(context: Any) -> None:
        before_attempts.append(context.attempt)

    def after_hook(context: Any) -> None:
        after_statuses.append(context.response.status_code)

    def error_hook(context: Any) -> None:
        error_types.append(type(context.error).__name__)

    monkeypatch.setattr(http_module.time, "sleep", lambda delay: sleep_calls.append(delay))

    client = HttpClient(
        base_url="https://api.test",
        client=requester,
        default_headers={"X-Default": "1"},
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("GET",),
            retry_on_network_error=True,
            base_delay_seconds=0.25,
        ),
        hooks=Hooks(
            before_request=before_hook,
            after_response=[after_hook],
            on_error=error_hook,
        ),
    )

    result = client.request(
        HttpRequestOptions(
            path="/items",
            method="GET",
            headers={"X-Extra": "2"},
            query={"page": 1},
            retry=True,
        )
    )

    assert result == {"ok": True}
    assert before_attempts == [1, 2]
    assert after_statuses == [200]
    assert error_types == ["TimeoutError"]
    assert sleep_calls == [0.25]
    assert requester.calls[0]["headers"] == {"X-Default": "1", "X-Extra": "2"}
    assert requester.calls[0]["params"] == {"page": 1}

    failing_requester = SequencedSyncRequester(
        actions=[
            httpx.ConnectError("boom", request=httpx.Request("POST", "https://api.test/fail"))
        ]
    )
    failing_client = HttpClient(base_url="https://api.test", client=failing_requester)
    with pytest.raises(NetworkError, match="Request failed"):
        failing_client.request(HttpRequestOptions(path="/fail", method="POST"))

    timeout_failure_client = HttpClient(
        base_url="https://api.test",
        client=SequencedSyncRequester(
            actions=[
                httpx.ReadTimeout(
                    "timed out",
                    request=httpx.Request("GET", "https://api.test/timeout"),
                )
            ]
        ),
        retry=RetryPolicy(max_attempts=1, retry_methods=("GET",), retry_on_network_error=True),
    )
    with pytest.raises(TimeoutError, match="Request timed out"):
        timeout_failure_client.request(HttpRequestOptions(path="/timeout", method="GET"))

    network_retry_client = HttpClient(
        base_url="https://api.test",
        client=SequencedSyncRequester(
            actions=[
                httpx.ConnectError(
                    "boom",
                    request=httpx.Request("GET", "https://api.test/network-retry"),
                ),
                make_response(200, {"ok": "network-retried"}),
            ]
        ),
        retry=RetryPolicy(max_attempts=2, retry_methods=("GET",), retry_on_network_error=True),
    )
    assert network_retry_client.request(
        HttpRequestOptions(path="/network-retry", method="GET")
    ) == {"ok": "network-retried"}

    api_retry_requester = SequencedSyncRequester(
        actions=[
            make_response(503, {"detail": "temporary"}),
            make_response(200, {"ok": "retried"}),
        ]
    )
    api_retry_client = HttpClient(
        base_url="https://api.test",
        client=api_retry_requester,
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("GET",),
            retry_on_statuses=(503,),
        ),
    )
    assert api_retry_client.request(HttpRequestOptions(path="/retry", method="GET")) == {
        "ok": "retried"
    }

    api_failure_client = HttpClient(
        base_url="https://api.test",
        client=SequencedSyncRequester(actions=[make_response(400, {"message": "bad request"})]),
    )
    with pytest.raises(ApiError, match="bad request") as exc:
        api_failure_client.request(HttpRequestOptions(path="/bad", method="GET"))
    assert exc.value.status_code == 400
    assert exc.value.response_body == {"message": "bad request"}

    owned_requester = SequencedSyncRequester(actions=[])
    monkeypatch.setattr(http_module.httpx, "Client", lambda: owned_requester)
    with HttpClient(base_url="https://api.test") as owned_client:
        assert owned_client.client is owned_requester
    assert owned_requester.closed is True

    stubborn_requester = SequencedSyncRequester(
        actions=[make_response(503, {"detail": "still bad"})]
    )
    stubborn_client = HttpClient(
        base_url="https://api.test",
        client=stubborn_requester,
        retry=RetryPolicy(max_attempts=1, retry_methods=("GET",), retry_on_statuses=(503,)),
    )
    monkeypatch.setattr(HttpClient, "_should_retry", lambda self, policy, context: True)
    monkeypatch.setattr(HttpClient, "_sleep_before_retry", lambda self, policy, attempt: None)
    with pytest.raises(RuntimeError, match="unreachable retry state"):
        stubborn_client.request(HttpRequestOptions(path="/never-stop", method="GET"))


def test_http_client_async_paths_cover_retries_hooks_and_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        timeout_request = httpx.Request("GET", "https://api.test/items")
        requester = SequencedAsyncRequester(
            actions=[
                httpx.ReadTimeout("timed out", request=timeout_request),
                make_response(200, {"ok": True}),
            ]
        )
        before_attempts: list[int] = []
        after_statuses: list[int] = []
        error_types: list[str] = []
        sleep_calls: list[float] = []

        def before_hook(context: Any) -> None:
            before_attempts.append(context.attempt)

        def after_hook(context: Any) -> None:
            after_statuses.append(context.response.status_code)

        def error_hook(context: Any) -> None:
            error_types.append(type(context.error).__name__)

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        monkeypatch.setattr(http_module.asyncio, "sleep", fake_sleep)

        client = AsyncHttpClient(
            base_url="https://api.test",
            client=requester,
            default_headers={"X-Default": "1"},
            retry=RetryPolicy(
                max_attempts=2,
                retry_methods=("GET",),
                retry_on_network_error=True,
                base_delay_seconds=0.5,
            ),
            hooks=Hooks(
                before_request=[before_hook],
                after_response=after_hook,
                on_error=[error_hook],
            ),
        )
        result = await client.request(
            HttpRequestOptions(
                path="/items",
                method="GET",
                headers={"X-Extra": "2"},
                query={"page": 2},
                retry=True,
            )
        )

        assert result == {"ok": True}
        assert before_attempts == [1, 2]
        assert after_statuses == [200]
        assert error_types == ["TimeoutError"]
        assert sleep_calls == [0.5]
        assert requester.calls[0]["headers"] == {"X-Default": "1", "X-Extra": "2"}

        network_client = AsyncHttpClient(
            base_url="https://api.test",
            client=SequencedAsyncRequester(
                actions=[
                    httpx.ConnectError(
                        "boom",
                        request=httpx.Request("POST", "https://api.test/fail"),
                    )
                ]
            ),
        )
        with pytest.raises(NetworkError, match="Request failed"):
            await network_client.request(HttpRequestOptions(path="/fail", method="POST"))

        timeout_failure_client = AsyncHttpClient(
            base_url="https://api.test",
            client=SequencedAsyncRequester(
                actions=[
                    httpx.ReadTimeout(
                        "timed out",
                        request=httpx.Request("GET", "https://api.test/timeout"),
                    )
                ]
            ),
            retry=RetryPolicy(max_attempts=1, retry_methods=("GET",), retry_on_network_error=True),
        )
        with pytest.raises(TimeoutError, match="Request timed out"):
            await timeout_failure_client.request(HttpRequestOptions(path="/timeout", method="GET"))

        network_retry_client = AsyncHttpClient(
            base_url="https://api.test",
            client=SequencedAsyncRequester(
                actions=[
                    httpx.ConnectError(
                        "boom",
                        request=httpx.Request("GET", "https://api.test/network-retry"),
                    ),
                    make_response(200, {"ok": "network-retried"}),
                ]
            ),
            retry=RetryPolicy(max_attempts=2, retry_methods=("GET",), retry_on_network_error=True),
        )
        assert await network_retry_client.request(
            HttpRequestOptions(path="/network-retry", method="GET")
        ) == {"ok": "network-retried"}

        api_retry_client = AsyncHttpClient(
            base_url="https://api.test",
            client=SequencedAsyncRequester(
                actions=[
                    make_response(503, {"detail": "temporary"}),
                    make_response(200, {"ok": "retried"}),
                ]
            ),
            retry=RetryPolicy(
                max_attempts=2,
                retry_methods=("GET",),
                retry_on_statuses=(503,),
            ),
        )
        assert await api_retry_client.request(HttpRequestOptions(path="/retry", method="GET")) == {
            "ok": "retried"
        }

        api_failure_client = AsyncHttpClient(
            base_url="https://api.test",
            client=SequencedAsyncRequester(actions=[make_response(400, {"detail": "bad"})]),
        )
        with pytest.raises(ApiError, match="bad") as exc:
            await api_failure_client.request(HttpRequestOptions(path="/bad", method="GET"))
        assert exc.value.status_code == 400
        assert exc.value.response_body == {"detail": "bad"}

        owned_requester = SequencedAsyncRequester(actions=[])
        monkeypatch.setattr(http_module.httpx, "AsyncClient", lambda: owned_requester)
        async with AsyncHttpClient(base_url="https://api.test") as owned_client:
            assert owned_client.client is owned_requester
        assert owned_requester.closed is True

        stubborn_client = AsyncHttpClient(
            base_url="https://api.test",
            client=SequencedAsyncRequester(actions=[make_response(503, {"detail": "still bad"})]),
            retry=RetryPolicy(max_attempts=1, retry_methods=("GET",), retry_on_statuses=(503,)),
        )

        async def no_sleep(self: AsyncHttpClient, policy: RetryPolicy | None, attempt: int) -> None:
            return None

        monkeypatch.setattr(AsyncHttpClient, "_should_retry", lambda self, policy, context: True)
        monkeypatch.setattr(AsyncHttpClient, "_sleep_before_retry", no_sleep)
        with pytest.raises(RuntimeError, match="unreachable retry state"):
            await stubborn_client.request(HttpRequestOptions(path="/never-stop", method="GET"))

    asyncio.run(run())


def test_sms_services_and_clients_cover_delegation_and_configuration_errors() -> None:
    request_options = RequestOptions(headers={"X-Test": "1"})
    send_request = SmsSendRequest(messages=[SmsMessage(recipient="254700000010", text="Hi")])
    group_request = SmsGroupUpsertRequest(name="Customers")
    template_request = SmsTemplateUpsertRequest(name="welcome", body="Hello")

    gateway = DummySmsManagementGateway()
    service = SmsService(gateway)
    assert service.configured is True
    assert service.provider == "dummy-sms"
    assert service.send(send_request, options=request_options).submitted_count == 1
    assert service.get_balance(options=request_options).provider == "dummy-sms"
    assert service.list_groups(options=request_options)[0].name == "Customers"
    assert service.create_group(group_request, options=request_options).message == "Customers"
    assert service.update_group("10", group_request, options=request_options).resource_id == "10"
    assert service.delete_group("10", options=request_options).resource_id == "10"
    assert service.list_templates(options=request_options)[0].name == "welcome"
    assert service.create_template(template_request, options=request_options).message == "welcome"
    assert (
        service.update_template("12", template_request, options=request_options).resource_id
        == "12"
    )
    assert service.delete_template("12", options=request_options).resource_id == "12"
    assert service.parse_delivery_report({"messageId": "sms-1"}).provider_message_id == "sms-1"
    service.close()
    assert gateway.closed is True

    base_gateway = DummySmsGateway()
    bare_service = SmsService(base_gateway)
    assert bare_service.configured is True
    assert bare_service.provider == "dummy-sms"
    with pytest.raises(ConfigurationError, match="group/template management"):
        bare_service.list_groups()

    unconfigured = SmsService(None)
    assert unconfigured.configured is False
    assert unconfigured.provider is None
    with pytest.raises(ConfigurationError, match="SMS gateway is not configured"):
        unconfigured.send(send_request)

    client_gateway = DummySmsManagementGateway()
    wa_gateway = DummyWhatsAppGateway()
    with MessagingClient(sms=client_gateway, whatsapp=wa_gateway) as client:
        assert client.sms.provider == "dummy-sms"
        assert client.whatsapp.provider == "dummy-wa"
    assert client_gateway.closed is True
    assert wa_gateway.closed is True


def test_async_sms_services_and_clients_cover_delegation_and_configuration_errors() -> None:
    async def run() -> None:
        request_options = RequestOptions(timeout_seconds=2.0)
        send_request = SmsSendRequest(
            messages=[SmsMessage(recipient="254700000011", text="Hi async")]
        )
        group_request = SmsGroupUpsertRequest(name="Leads")
        template_request = SmsTemplateUpsertRequest(name="promo", body="Save more")

        gateway = DummyAsyncSmsManagementGateway()
        service = AsyncSmsService(gateway)
        assert service.configured is True
        assert service.provider == "dummy-sms"
        assert (await service.send(send_request, options=request_options)).submitted_count == 1
        assert (await service.get_balance(options=request_options)).provider == "dummy-sms"
        assert (await service.list_groups(options=request_options))[0].name == "Leads"
        assert (await service.create_group(group_request, options=request_options)).message == (
            "Leads"
        )
        assert (
            await service.update_group("20", group_request, options=request_options)
        ).resource_id == "20"
        assert (await service.delete_group("20", options=request_options)).resource_id == "20"
        assert (await service.list_templates(options=request_options))[0].name == "promo"
        assert (
            await service.create_template(template_request, options=request_options)
        ).message == "promo"
        assert (
            await service.update_template("21", template_request, options=request_options)
        ).resource_id == "21"
        assert (await service.delete_template("21", options=request_options)).resource_id == "21"
        assert service.parse_delivery_report({"messageId": "sms-async-1"}).provider_message_id == (
            "sms-async-1"
        )
        await service.aclose()
        assert gateway.closed is True

        bare_service = AsyncSmsService(DummyAsyncSmsGateway())
        with pytest.raises(ConfigurationError, match="group/template management"):
            await bare_service.list_groups()

        unconfigured = AsyncSmsService(None)
        assert unconfigured.configured is False
        assert unconfigured.provider is None
        with pytest.raises(ConfigurationError, match="SMS gateway is not configured"):
            await unconfigured.send(send_request)

        sms_gateway = DummyAsyncSmsManagementGateway()
        wa_gateway = DummyAsyncWhatsAppGateway()
        async with AsyncMessagingClient(sms=sms_gateway, whatsapp=wa_gateway) as client:
            assert client.sms.provider == "dummy-sms"
            assert client.whatsapp.provider == "dummy-wa"
        assert sms_gateway.closed is True
        assert wa_gateway.closed is True

    asyncio.run(run())


def test_whatsapp_services_models_and_configuration_errors() -> None:
    text_request = WhatsAppTextRequest(recipient="254700000012", text="hello")
    template_request = WhatsAppTemplateRequest(
        recipient="254700000012",
        template_name="greeting",
        language_code="en_US",
    )
    template_list_request = WhatsAppTemplateListRequest(
        status=("approved", "paused"),
        fields=("name", "status"),
        limit=20,
    )
    template_create_request = WhatsAppTemplateCreateRequest(
        name="shipment_update",
        language="en_US",
        category="utility",
        components=(
            WhatsAppTemplateComponentDefinition(
                type="body",
                text="Hello {{1}}",
                example={"body_text": [["Alice"]]},
            ),
            WhatsAppTemplateComponentDefinition(
                type="buttons",
                buttons=(
                    WhatsAppTemplateButtonDefinition(type="quick_reply", text="Track"),
                ),
            ),
        ),
        parameter_format="positional",
    )
    template_update_request = WhatsAppTemplateUpdateRequest(
        category="marketing",
        components=(
            WhatsAppTemplateComponentDefinition(type="body", text="Updated {{1}}"),
        ),
    )
    template_delete_request = WhatsAppTemplateDeleteRequest(
        name="shipment_update",
        template_id="wa-template-2",
    )
    media_request = WhatsAppMediaRequest(
        recipient="254700000012",
        media_type="image",
        media_id="media-1",
    )
    location_request = WhatsAppLocationRequest(
        recipient="254700000012",
        latitude=-1.286389,
        longitude=36.817223,
    )
    contacts_request = WhatsAppContactsRequest(
        recipient="254700000012",
        contacts=(
            WhatsAppContact(
                name=WhatsAppContactName(formatted_name="Alice Example"),
                phones=(WhatsAppContactPhone(phone="+254700000012"),),
            ),
        ),
    )
    reaction_request = WhatsAppReactionRequest(
        recipient="254700000012",
        message_id="wamid.original",
        emoji="👍",
    )
    interactive_request = WhatsAppInteractiveRequest(
        recipient="254700000012",
        interactive_type="button",
        body_text="Choose one",
        buttons=(WhatsAppInteractiveButton(identifier="opt-1", title="Option 1"),),
    )
    catalog_request = WhatsAppCatalogMessageRequest(
        recipient="254700000012",
        body_text="Browse",
        thumbnail_product_retailer_id="sku-1",
    )
    product_request = WhatsAppProductMessageRequest(
        recipient="254700000012",
        catalog_id="catalog-1",
        product_retailer_id="sku-1",
    )
    product_list_request = WhatsAppProductListRequest(
        recipient="254700000012",
        catalog_id="catalog-1",
        header=WhatsAppInteractiveHeader(type="text", text="Store"),
        sections=(
            WhatsAppProductSection(
                title="Popular",
                product_items=(WhatsAppProductItem(product_retailer_id="sku-1"),),
            ),
        ),
    )
    flow_request = WhatsAppFlowMessageRequest(
        recipient="254700000012",
        flow_id="flow-1",
        flow_cta="Open flow",
    )
    media_upload_request = WhatsAppMediaUploadRequest(
        filename="poster.png",
        content=b"poster",
        mime_type="image/png",
    )
    options = RequestOptions(headers={"X-Test": "1"})

    gateway = DummyWhatsAppGateway()
    service = WhatsAppService(gateway)
    assert service.configured is True
    assert service.provider == "dummy-wa"
    assert service.send_text(text_request, options=options).submitted_count == 1
    assert service.send_template(template_request, options=options).failed_count == 1
    assert (
        service.list_templates(template_list_request, options=options).templates[0].template_id
        == "wa-template-1"
    )
    assert (
        service.get_template("wa-template-1", fields=("name",), options=options).parameter_format
        == "POSITIONAL"
    )
    assert (
        service.create_template(template_create_request, options=options).template_id
        == "wa-template-2"
    )
    assert (
        service.update_template(
            "wa-template-2",
            template_update_request,
            options=options,
        ).category
        == "MARKETING"
    )
    assert service.delete_template(template_delete_request, options=options).deleted is True
    assert service.send_media(media_request, options=options).submitted_count == 1
    assert service.send_location(location_request, options=options).submitted_count == 1
    assert service.send_contacts(contacts_request, options=options).submitted_count == 1
    assert service.send_reaction(reaction_request, options=options).submitted_count == 1
    assert service.send_interactive(interactive_request, options=options).submitted_count == 1
    assert service.send_catalog(catalog_request, options=options).submitted_count == 1
    assert service.send_product(product_request, options=options).submitted_count == 1
    assert service.send_product_list(product_list_request, options=options).submitted_count == 1
    assert service.send_flow(flow_request, options=options).submitted_count == 1
    assert service.upload_media(media_upload_request, options=options).media_id == "media-upload-1"
    assert service.get_media("media-1", options=options).media_id == "media-1"
    assert service.delete_media("media-1", options=options).deleted is True
    assert service.parse_events({"entry": []})[0].provider_message_id == "wa-evt-1"
    assert service.parse_event({"entry": []}).provider_message_id == "wa-evt-1"
    assert service.parse_inbound_messages({"entry": []})[0].message_id == "wamid.inbound"
    assert service.parse_inbound_message({"entry": []}).message_id == "wamid.inbound"
    service.close()
    assert gateway.closed is True

    class EmptyWhatsAppGateway(DummyWhatsAppGateway):
        def parse_events(self, payload: dict[str, object]) -> tuple[DeliveryEvent, ...]:
            return ()

        def parse_inbound_messages(
            self,
            payload: dict[str, object],
        ) -> tuple[WhatsAppInboundMessage, ...]:
            return ()

    assert WhatsAppService(EmptyWhatsAppGateway()).parse_event({}) is None
    assert WhatsAppService(EmptyWhatsAppGateway()).parse_inbound_message({}) is None

    unconfigured = WhatsAppService(None)
    assert unconfigured.configured is False
    assert unconfigured.provider is None
    with pytest.raises(ConfigurationError, match="WhatsApp gateway is not configured"):
        unconfigured.send_text(text_request)
    with pytest.raises(ConfigurationError, match="template management"):
        WhatsAppService(object()).list_templates()
    with pytest.raises(
        ConfigurationError,
        match="requires whatsapp_business_account_id",
    ):
        WhatsAppService(
            MetaWhatsAppGateway(access_token="meta-token", phone_number_id="123456789")
        ).list_templates()

    result = WhatsAppSendResult(
        provider="dummy-wa",
        accepted=True,
        error_code=None,
        error_description=None,
        messages=(
            WhatsAppSendReceipt(
                provider="dummy-wa",
                recipient="254700000012",
                status="submitted",
                provider_message_id="wa-1",
            ),
            WhatsAppSendReceipt(
                provider="dummy-wa",
                recipient="254700000013",
                status="failed",
                provider_message_id="wa-2",
            ),
        ),
    )
    assert result.submitted_count == 1
    assert result.failed_count == 1


def test_async_whatsapp_services_cover_delegation_and_configuration_errors() -> None:
    async def run() -> None:
        text_request = WhatsAppTextRequest(recipient="254700000014", text="hello async")
        template_request = WhatsAppTemplateRequest(
            recipient="254700000014",
            template_name="promo",
            language_code="en_US",
        )
        template_list_request = WhatsAppTemplateListRequest(
            status=("approved",),
            fields=("name", "category"),
        )
        template_create_request = WhatsAppTemplateCreateRequest(
            name="shipment_update_async",
            language="en_US",
            category="utility",
            components=(
                WhatsAppTemplateComponentDefinition(type="body", text="Hello {{1}}"),
            ),
            parameter_format="positional",
        )
        template_update_request = WhatsAppTemplateUpdateRequest(
            category="marketing",
            components=(
                WhatsAppTemplateComponentDefinition(type="body", text="Updated {{1}}"),
            ),
        )
        template_delete_request = WhatsAppTemplateDeleteRequest(
            name="shipment_update_async",
            template_id="wa-template-async-2",
        )
        media_request = WhatsAppMediaRequest(
            recipient="254700000014",
            media_type="document",
            media_id="media-async-1",
            filename="guide.pdf",
        )
        location_request = WhatsAppLocationRequest(
            recipient="254700000014",
            latitude=-1.2,
            longitude=36.8,
        )
        contacts_request = WhatsAppContactsRequest(
            recipient="254700000014",
            contacts=(
                WhatsAppContact(
                    name=WhatsAppContactName(formatted_name="Async Contact"),
                    phones=(WhatsAppContactPhone(phone="+254700000014"),),
                ),
            ),
        )
        reaction_request = WhatsAppReactionRequest(
            recipient="254700000014",
            message_id="wamid.async.original",
            emoji="🔥",
        )
        interactive_request = WhatsAppInteractiveRequest(
            recipient="254700000014",
            interactive_type="button",
            body_text="Pick",
            buttons=(WhatsAppInteractiveButton(identifier="async-1", title="Async 1"),),
        )
        catalog_request = WhatsAppCatalogMessageRequest(
            recipient="254700000014",
            body_text="Browse async",
        )
        product_request = WhatsAppProductMessageRequest(
            recipient="254700000014",
            catalog_id="catalog-1",
            product_retailer_id="sku-1",
        )
        product_list_request = WhatsAppProductListRequest(
            recipient="254700000014",
            catalog_id="catalog-1",
            header=WhatsAppInteractiveHeader(type="text", text="Async Store"),
            sections=(
                WhatsAppProductSection(
                    title="Featured",
                    product_items=(WhatsAppProductItem(product_retailer_id="sku-1"),),
                ),
            ),
        )
        flow_request = WhatsAppFlowMessageRequest(
            recipient="254700000014",
            flow_name="lead_capture",
            flow_cta="Open async flow",
        )
        media_upload_request = WhatsAppMediaUploadRequest(
            filename="async.pdf",
            content=b"pdf",
            mime_type="application/pdf",
        )
        options = RequestOptions(timeout_seconds=3.0)

        gateway = DummyAsyncWhatsAppGateway()
        service = AsyncWhatsAppService(gateway)
        assert service.configured is True
        assert service.provider == "dummy-wa"
        assert (await service.send_text(text_request, options=options)).submitted_count == 1
        assert (await service.send_template(template_request, options=options)).failed_count == 1
        assert (
            await service.list_templates(template_list_request, options=options)
        ).templates[0].template_id == "wa-template-async-1"
        assert (
            await service.get_template(
                "wa-template-async-1",
                fields=("name",),
                options=options,
            )
        ).parameter_format == "POSITIONAL"
        assert (
            await service.create_template(template_create_request, options=options)
        ).template_id == "wa-template-async-2"
        assert (
            await service.update_template(
                "wa-template-async-2",
                template_update_request,
                options=options,
            )
        ).category == "MARKETING"
        assert (
            await service.delete_template(template_delete_request, options=options)
        ).deleted is True
        assert (await service.send_media(media_request, options=options)).submitted_count == 1
        assert (await service.send_location(location_request, options=options)).submitted_count == 1
        assert (await service.send_contacts(contacts_request, options=options)).submitted_count == 1
        assert (await service.send_reaction(reaction_request, options=options)).submitted_count == 1
        assert (
            await service.send_interactive(interactive_request, options=options)
        ).submitted_count == 1
        assert (await service.send_catalog(catalog_request, options=options)).submitted_count == 1
        assert (await service.send_product(product_request, options=options)).submitted_count == 1
        assert (
            await service.send_product_list(product_list_request, options=options)
        ).submitted_count == 1
        assert (await service.send_flow(flow_request, options=options)).submitted_count == 1
        assert (
            await service.upload_media(media_upload_request, options=options)
        ).media_id == "media-upload-async-1"
        assert (await service.get_media("media-async-1", options=options)).media_id == (
            "media-async-1"
        )
        assert (await service.delete_media("media-async-1", options=options)).deleted is True
        assert service.parse_events({})[0].provider_message_id == "wa-evt-async-1"
        assert service.parse_event({}).provider_message_id == "wa-evt-async-1"
        assert service.parse_inbound_messages({})[0].message_id == "wamid.inbound.async"
        assert service.parse_inbound_message({}).message_id == "wamid.inbound.async"
        await service.aclose()
        assert gateway.closed is True

        class EmptyAsyncWhatsAppGateway(DummyAsyncWhatsAppGateway):
            def parse_events(self, payload: dict[str, object]) -> tuple[DeliveryEvent, ...]:
                return ()

            def parse_inbound_messages(
                self,
                payload: dict[str, object],
            ) -> tuple[WhatsAppInboundMessage, ...]:
                return ()

        assert AsyncWhatsAppService(EmptyAsyncWhatsAppGateway()).parse_event({}) is None
        assert AsyncWhatsAppService(EmptyAsyncWhatsAppGateway()).parse_inbound_message({}) is None

        unconfigured = AsyncWhatsAppService(None)
        assert unconfigured.configured is False
        assert unconfigured.provider is None
        with pytest.raises(ConfigurationError, match="WhatsApp gateway is not configured"):
            await unconfigured.send_text(text_request)
        with pytest.raises(ConfigurationError, match="template management"):
            await AsyncWhatsAppService(object()).list_templates()
        with pytest.raises(
            ConfigurationError,
            match="requires whatsapp_business_account_id",
        ):
            await AsyncWhatsAppService(
                MetaWhatsAppGateway(access_token="meta-token", phone_number_id="123456789")
            ).list_templates()

    asyncio.run(run())


def test_onfon_gateway_sync_management_and_helper_paths() -> None:
    client = SequencedSyncRequester(
        actions=[
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [{"PluginType": "SMS", "Credits": "KSh12.50"}],
                },
            ),
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [
                        {"GroupId": "1", "GroupName": "Customers", "ContactCount": "5"},
                        {"GroupId": None, "GroupName": "Ignored", "ContactCount": "x"},
                    ],
                },
            ),
            make_response(
                200,
                {"ErrorCode": 0, "ErrorDescription": "success#Created", "Data": None},
            ),
            make_response(
                200,
                {"ErrorCode": 0, "ErrorDescription": "success#Updated", "Data": ""},
            ),
            make_response(
                200,
                {"ErrorCode": 0, "ErrorDescription": "success#Deleted", "Data": ""},
            ),
            make_response(
                200,
                {
                    "ErrorCode": 0,
                    "ErrorDescription": "Success",
                    "Data": [
                        {
                            "TemplateId": "2",
                            "TemplateName": "promo",
                            "MessageTemplate": "Hello",
                            "IsApproved": "yes",
                            "IsActive": "0",
                            "CreatededDate": "2026-04-07",
                            "ApprovedDate": "2026-04-08",
                        },
                        {
                            "TemplateId": None,
                            "TemplateName": "Ignored",
                            "MessageTemplate": "Ignored",
                        },
                    ],
                },
            ),
            make_response(
                200,
                {"ErrorCode": 0, "ErrorDescription": "success#Created", "Data": "created"},
            ),
            make_response(
                200,
                {"ErrorCode": 0, "ErrorDescription": "success#Updated", "Data": ""},
            ),
            make_response(
                200,
                {"ErrorCode": 0, "ErrorDescription": "success#Deleted", "Data": ""},
            ),
        ]
    )

    gateway = OnfonSmsGateway(
        access_key="access-key",
        api_key="api-key",
        client_id="client-id",
        default_sender_id="NORIA",
        client=client,
    )

    assert gateway.get_balance().entries[0].credits == Decimal("12.50")
    groups = gateway.list_groups()
    assert len(groups) == 1
    assert groups[0].group_id == "1"
    assert groups[0].name == "Customers"
    assert groups[0].contact_count == 5
    assert gateway.create_group(
        SmsGroupUpsertRequest(name="Customers", provider_options={"Tag": "vip"})
    ).message == "success#Created"
    assert gateway.update_group("1", SmsGroupUpsertRequest(name="Leads")).resource_id == "1"
    assert gateway.delete_group("1").resource_id == "1"
    templates = gateway.list_templates()
    assert templates[0].approved is True
    assert templates[0].active is False
    assert gateway.create_template(
        SmsTemplateUpsertRequest(name="promo", body="Hello ##Name##")
    ).message == "created"
    assert gateway.update_template(
        "2",
        SmsTemplateUpsertRequest(name="promo-updated", body="Updated"),
    ).resource_id == "2"
    assert gateway.delete_template("2").resource_id == "2"
    assert gateway.parse_delivery_report({}) is None
    gateway.close()
    assert client.closed is False

    gateway._http = HttpClient(base_url="https://api.test", client=client)
    gateway.close()
    assert client.closed is False

    with pytest.raises(GatewayError, match="non-object response"):
        gateway._validate_response([])
    with pytest.raises(GatewayError, match="Provider request failed"):
        gateway._validate_response({"ErrorCode": 1, "ErrorDescription": None})
    with pytest.raises(ValueError, match="messages must not be empty"):
        _validate_send_request(SmsSendRequest(messages=[]))
    with pytest.raises(ValueError, match="messages\\[0\\].recipient must not be empty"):
        _validate_send_request(SmsSendRequest(messages=[SmsMessage(recipient=" ", text="Hi")]))
    with pytest.raises(ValueError, match="messages\\[0\\].text must not be empty"):
        _validate_send_request(SmsSendRequest(messages=[SmsMessage(recipient="2547", text=" ")]))
    with pytest.raises(ConfigurationError, match="name is required"):
        require_onfon_text(None, "name")
    with pytest.raises(ValueError, match="group_id is required"):
        require_onfon_identifier(None, "group_id")
    assert _normalize_error_code(None) is None
    assert _normalize_error_code("7") == "007"
    assert _normalize_error_code("E01") == "E01"
    assert _coerce_int(None) is None
    assert _coerce_int("bad") is None
    assert _coerce_int("9") == 9
    assert _coerce_bool(True) is True
    assert _coerce_bool(None) is None
    assert _coerce_bool("1") is True
    assert _coerce_bool("0") is False
    assert _coerce_bool("maybe") is None
    assert _is_success_payload({"ErrorCode": 0, "ErrorDescription": "Success"}) is True
    assert _is_success_payload({"ErrorCode": 0, "ErrorDescription": None}) is True
    assert _is_success_payload({"ErrorCode": "2", "ErrorDescription": "Failed"}) is False
    assert _is_success_code(None) is False
    assert _is_success_code("0") is True
    assert _is_success_code("x") is False
    assert _map_delivery_state(None) == "unknown"
    assert _map_delivery_state("DELIVERED") == "delivered"
    assert _map_delivery_state("accepted") == "submitted"
    assert _map_delivery_state("FAILED") == "failed"
    assert _map_delivery_state("OTHER") == "unknown"
    assert gateway._build_template_list({"Data": None}) == ()


def test_onfon_gateway_async_management_and_close_paths() -> None:
    async def run() -> None:
        async_client = SequencedAsyncRequester(
            actions=[
                make_response(
                    200,
                    {
                        "ErrorCode": 0,
                        "ErrorDescription": "Success",
                        "Data": [{"PluginType": "SMS", "Credits": "KSh20.00"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "ErrorCode": 0,
                        "ErrorDescription": "Success",
                        "Data": [{"GroupId": "3", "GroupName": "Async", "ContactCount": 2}],
                    },
                ),
                make_response(
                    200,
                    {"ErrorCode": 0, "ErrorDescription": "success#Created", "Data": "ok"},
                ),
                make_response(
                    200,
                    {"ErrorCode": 0, "ErrorDescription": "success#Updated", "Data": ""},
                ),
                make_response(
                    200,
                    {"ErrorCode": 0, "ErrorDescription": "success#Deleted", "Data": ""},
                ),
                make_response(
                    200,
                    {
                        "ErrorCode": 0,
                        "ErrorDescription": "Success",
                        "Data": [
                            {
                                "TemplateId": "4",
                                "TemplateName": "async",
                                "MessageTemplate": "Body",
                                "IsApproved": True,
                                "IsActive": False,
                            }
                        ],
                    },
                ),
                make_response(
                    200,
                    {"ErrorCode": 0, "ErrorDescription": "success#Created", "Data": "ok"},
                ),
                make_response(
                    200,
                    {"ErrorCode": 0, "ErrorDescription": "success#Updated", "Data": ""},
                ),
                make_response(
                    200,
                    {"ErrorCode": 0, "ErrorDescription": "success#Deleted", "Data": ""},
                ),
            ]
        )
        gateway = OnfonSmsGateway(
            access_key="access-key",
            api_key="api-key",
            client_id="client-id",
            default_sender_id="NORIA",
            async_client=async_client,
        )

        assert (await gateway.aget_balance()).entries[0].credits == Decimal("20.00")
        assert (await gateway.alist_groups())[0].name == "Async"
        assert (await gateway.acreate_group(SmsGroupUpsertRequest(name="Async"))).message == "ok"
        assert (
            await gateway.aupdate_group("3", SmsGroupUpsertRequest(name="Async-updated"))
        ).resource_id == "3"
        assert (await gateway.adelete_group("3")).resource_id == "3"
        assert (await gateway.alist_templates())[0].template_id == "4"
        assert (
            await gateway.acreate_template(SmsTemplateUpsertRequest(name="a", body="b"))
        ).message == "ok"
        assert (
            await gateway.aupdate_template("4", SmsTemplateUpsertRequest(name="a", body="b"))
        ).resource_id == "4"
        assert (await gateway.adelete_template("4")).resource_id == "4"

        await gateway.aclose()
        assert async_client.closed is False
        gateway._async_http = AsyncHttpClient(base_url="https://api.test", client=async_client)
        await gateway.aclose()
        assert async_client.closed is False

    asyncio.run(run())


def test_meta_gateway_sync_async_helpers_and_parser_paths() -> None:
    async def run() -> None:
        sync_client = SequencedSyncRequester(
            actions=[
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000020"}],
                        "messages": [{"id": "wamid.1", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000020"}],
                        "messages": [{"id": "wamid.2", "message_status": "sent"}],
                    },
                ),
            ]
        )
        async_client = SequencedAsyncRequester(
            actions=[
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.3", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.4", "message_status": "sent"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.5", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.6", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.7", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.8", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.9", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.10", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.11", "message_status": "accepted"}],
                    },
                ),
                make_response(
                    200,
                    {
                        "contacts": [{"wa_id": "254700000021"}],
                        "messages": [{"id": "wamid.12", "message_status": "accepted"}],
                    },
                ),
                make_response(200, {"id": "media.async.1"}),
                make_response(
                    200,
                    {
                        "id": "media.async.1",
                        "url": "https://lookaside.fbsbx.com/media/async-1",
                        "mime_type": "image/png",
                        "sha256": "async-sha",
                        "file_size": "512",
                    },
                ),
                make_response(200, {"success": True}),
            ]
        )
        gateway = MetaWhatsAppGateway(
            access_token="token",
            phone_number_id="12345",
            app_secret="app-secret",
            client=sync_client,
            async_client=async_client,
        )

        assert gateway.send_text(
            WhatsAppTextRequest(recipient="254700000020", text="Hello sync")
        ).messages[0].provider_message_id == "wamid.1"
        assert gateway.send_template(
            WhatsAppTemplateRequest(
                recipient="254700000020",
                template_name="promo",
                language_code="en_US",
                reply_to_message_id="wamid.parent",
                components=[
                    WhatsAppTemplateComponent(
                        type="button",
                        sub_type="quick_reply",
                        index=0,
                        parameters=[
                            WhatsAppTemplateParameter(type="payload", value="payload-1"),
                        ],
                    )
                ],
            )
        ).messages[0].provider_message_id == "wamid.2"
        assert (
            await gateway.asend_text(
                WhatsAppTextRequest(recipient="254700000021", text="Hello async")
            )
        ).messages[0].provider_message_id == "wamid.3"
        assert (
            await gateway.asend_template(
                WhatsAppTemplateRequest(
                    recipient="254700000021",
                    template_name="promo",
                    language_code="en_US",
                )
            )
        ).messages[0].provider_message_id == "wamid.4"
        assert (
            await gateway.asend_location(
                WhatsAppLocationRequest(
                    recipient="254700000021",
                    latitude=-1.286389,
                    longitude=36.817223,
                )
            )
        ).messages[0].provider_message_id == "wamid.5"
        assert (
            await gateway.asend_contacts(
                WhatsAppContactsRequest(
                    recipient="254700000021",
                    contacts=(
                        WhatsAppContact(
                            name=WhatsAppContactName(formatted_name="Async Alice"),
                            phones=(WhatsAppContactPhone(phone="+254700000021"),),
                        ),
                    ),
                )
            )
        ).messages[0].provider_message_id == "wamid.6"
        assert (
            await gateway.asend_reaction(
                WhatsAppReactionRequest(
                    recipient="254700000021",
                    message_id="wamid.parent",
                    emoji="✅",
                )
            )
        ).messages[0].provider_message_id == "wamid.7"
        assert (
            await gateway.asend_interactive(
                WhatsAppInteractiveRequest(
                    recipient="254700000021",
                    interactive_type="button",
                    body_text="Pick one",
                    buttons=(
                        WhatsAppInteractiveButton(
                            identifier="choice-1",
                            title="Choice 1",
                        ),
                    ),
                )
            )
        ).messages[0].provider_message_id == "wamid.8"
        assert (
            await gateway.asend_catalog(
                WhatsAppCatalogMessageRequest(
                    recipient="254700000021",
                    body_text="Browse async",
                )
            )
        ).messages[0].provider_message_id == "wamid.9"
        assert (
            await gateway.asend_product(
                WhatsAppProductMessageRequest(
                    recipient="254700000021",
                    catalog_id="catalog-1",
                    product_retailer_id="sku-1",
                )
            )
        ).messages[0].provider_message_id == "wamid.10"
        assert (
            await gateway.asend_product_list(
                WhatsAppProductListRequest(
                    recipient="254700000021",
                    catalog_id="catalog-1",
                    header=WhatsAppInteractiveHeader(type="text", text="Store"),
                    sections=(
                        WhatsAppProductSection(
                            title="Popular",
                            product_items=(WhatsAppProductItem(product_retailer_id="sku-1"),),
                        ),
                    ),
                )
            )
        ).messages[0].provider_message_id == "wamid.11"
        assert (
            await gateway.asend_flow(
                WhatsAppFlowMessageRequest(
                    recipient="254700000021",
                    flow_name="lead_capture",
                    flow_cta="Open flow",
                )
            )
        ).messages[0].provider_message_id == "wamid.12"
        assert (
            await gateway.aupload_media(
                WhatsAppMediaUploadRequest(
                    filename="poster.png",
                    content=b"png",
                    mime_type="image/png",
                )
            )
        ).media_id == "media.async.1"
        assert (await gateway.aget_media("media.async.1")).file_size == 512
        assert (await gateway.adelete_media("media.async.1")).deleted is True
        assert gateway._messages_path() == f"/{gateway.api_version}/12345/messages"
        assert gateway._media_upload_path() == f"/{gateway.api_version}/12345/media"
        assert gateway._media_path("media.async.1") == f"/{gateway.api_version}/media.async.1"
        assert gateway._media_query() == {"phone_number_id": "12345"}

        events = gateway.parse_events(
            {
                "entry": [
                    {"changes": "invalid"},
                    {
                        "changes": [
                            {"value": {"statuses": "invalid"}},
                            {
                                "value": {
                                    "statuses": [
                                        {"status": "delivered"},
                                        {
                                            "id": "wamid.status.1",
                                            "status": "failed",
                                            "recipient_id": "254700000099",
                                            "timestamp": "1712475856",
                                            "errors": [{"code": "470", "title": "No route"}],
                                            "conversation": {"origin": {}},
                                            "pricing": {"category": "utility"},
                                        },
                                    ]
                                }
                            },
                        ]
                    },
                ]
            }
        )
        assert len(events) == 1
        assert events[0].state == "failed"
        assert events[0].error_code == "470"
        assert events[0].error_description == "No route"
        assert gateway.parse_events({"entry": "invalid"}) == ()
        assert gateway.parse_event({"entry": []}) is None
        assert (
            gateway.parse_inbound_messages(
                {
                    "entry": [
                        {
                            "changes": [
                                {
                                    "value": {
                                        "messages": "invalid",
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            == ()
        )
        assert gateway.parse_event(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "statuses": [
                                        {
                                            "id": "wamid.status.2",
                                            "status": "read",
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ).state == "read"

        with pytest.raises(GatewayError, match="did not return a message id"):
            gateway._build_send_result("254700000020", {"messages": [{}]})
        with pytest.raises(GatewayError, match="non-object response"):
            gateway._validate_response([])
        with pytest.raises(GatewayError, match="Provider request failed"):
            gateway._validate_response({"error": {"code": "190"}})
        with pytest.raises(GatewayError, match="user-visible"):
            gateway._validate_response(
                {
                    "error": {
                        "code": "190",
                        "error_user_msg": "user-visible",
                        "message": "fallback",
                    }
                }
            )

        assert _build_text_payload(
            WhatsAppTextRequest(
                recipient="254700000022",
                text="Hello",
                preview_url=True,
                reply_to_message_id="wamid.reply",
                provider_options={"biz_opaque_callback_data": "cb-1"},
            )
        ) == {
            "biz_opaque_callback_data": "cb-1",
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "254700000022",
            "type": "text",
            "text": {"body": "Hello", "preview_url": True},
            "context": {"message_id": "wamid.reply"},
        }
        assert _build_template_payload(
            WhatsAppTemplateRequest(
                recipient="254700000023",
                template_name="promo",
                language_code="en_US",
                reply_to_message_id="wamid.parent",
                provider_options={"biz_opaque_callback_data": "cb-2"},
                components=[
                    WhatsAppTemplateComponent(
                        type="button",
                        sub_type="quick_reply",
                        index=1,
                        parameters=(
                            WhatsAppTemplateParameter(type="text", value="Alice"),
                            WhatsAppTemplateParameter(type="payload", value="p-1"),
                            WhatsAppTemplateParameter(type="image", value="media-1"),
                            WhatsAppTemplateParameter(
                                type="image",
                                value="ignored",
                                provider_options={"image": {"link": "https://cdn.test/image.png"}},
                            ),
                            WhatsAppTemplateParameter(type="currency", value="KES 100"),
                            WhatsAppTemplateParameter(type="text"),
                        ),
                    )
                ],
            )
        )["template"]["components"][0]["parameters"] == [
            {"type": "text", "text": "Alice"},
            {"type": "payload", "payload": "p-1"},
            {"type": "image", "image": {"id": "media-1"}},
            {"image": {"link": "https://cdn.test/image.png"}, "type": "image"},
            {"type": "currency", "text": "KES 100"},
            {"type": "text"},
        ]
        assert _build_template_component(WhatsAppTemplateComponent(type="body")) == {"type": "body"}
        assert _build_template_parameter(WhatsAppTemplateParameter(type="payload", value="x")) == {
            "type": "payload",
            "payload": "x",
        }
        assert _first_mapping([]) == {}
        assert _first_mapping({"id": "1"}) == {"id": "1"}
        assert _map_whatsapp_state("accepted") == "submitted"
        assert _map_whatsapp_state("sent") == "submitted"
        assert _map_whatsapp_state("delivered") == "delivered"
        assert _map_whatsapp_state("read") == "read"
        assert _map_whatsapp_state("failed") == "failed"
        assert _map_whatsapp_state(None) == "unknown"
        with pytest.raises(ConfigurationError, match="recipient is required"):
            require_meta_text(" ", "recipient")

        gateway.close()
        await gateway.aclose()
        assert sync_client.closed is False
        assert async_client.closed is False
        gateway._http = HttpClient(base_url="https://api.test", client=sync_client)
        gateway._async_http = AsyncHttpClient(base_url="https://api.test", client=async_client)
        gateway.close()
        await gateway.aclose()
        assert sync_client.closed is False
        assert async_client.closed is False

    asyncio.run(run())


def test_meta_gateway_builder_and_inbound_edge_paths() -> None:
    full_contact = WhatsAppContact(
        name=WhatsAppContactName(
            formatted_name="Alice Example",
            first_name="Alice",
            last_name="Example",
        ),
        phones=(WhatsAppContactPhone(phone="+254700000031", type="CELL", wa_id="254700000031"),),
        emails=(WhatsAppContactEmail(email="alice@example.com", type="WORK"),),
        urls=(WhatsAppContactUrl(url="https://example.com/alice", type="WORK"),),
        addresses=(
            WhatsAppContactAddress(
                street="1 Main Street",
                city="Nairobi",
                state="Nairobi",
                zip="00100",
                country="Kenya",
                country_code="KE",
                type="HOME",
            ),
        ),
        org=WhatsAppContactOrg(company="Noria", department="Growth", title="Lead"),
        birthday="1990-01-01",
    )

    contacts_payload = meta_gateway_module._build_contacts_payload(
        WhatsAppContactsRequest(
            recipient="254700000031",
            contacts=(full_contact,),
            provider_options={"biz_opaque_callback_data": "cb-contacts"},
        )
    )
    assert contacts_payload["biz_opaque_callback_data"] == "cb-contacts"
    assert contacts_payload["contacts"][0]["emails"][0] == {
        "email": "alice@example.com",
        "type": "WORK",
    }
    assert contacts_payload["contacts"][0]["urls"][0] == {
        "url": "https://example.com/alice",
        "type": "WORK",
    }
    assert contacts_payload["contacts"][0]["org"] == {
        "company": "Noria",
        "department": "Growth",
        "title": "Lead",
    }
    assert contacts_payload["contacts"][0]["birthday"] == "1990-01-01"
    with pytest.raises(ValueError, match="contacts must not be empty"):
        meta_gateway_module._build_contacts_payload(
            WhatsAppContactsRequest(recipient="254700000031", contacts=())
        )

    with pytest.raises(ValueError, match="either media_id or link"):
        meta_gateway_module._build_media_object(
            media_id="media-1",
            link="https://cdn.test/file.pdf",
            field_name="media",
        )
    with pytest.raises(ValueError, match="requires either media_id or link"):
        meta_gateway_module._build_media_object(media_id=None, link=None, field_name="media")

    interactive_payload = meta_gateway_module._build_interactive_payload(
        WhatsAppInteractiveRequest(
            recipient="254700000031",
            interactive_type="button",
            body_text="Choose your path",
            header=WhatsAppInteractiveHeader(
                type="document",
                link="https://cdn.test/guide.pdf",
                filename="guide.pdf",
            ),
            buttons=(WhatsAppInteractiveButton(identifier="choice-1", title="Choice 1"),),
        )
    )
    assert interactive_payload["interactive"]["header"] == {
        "type": "document",
        "document": {
            "link": "https://cdn.test/guide.pdf",
            "filename": "guide.pdf",
        },
    }
    assert interactive_payload["interactive"]["action"]["buttons"][0] == {
        "type": "reply",
        "reply": {"id": "choice-1", "title": "Choice 1"},
    }
    with pytest.raises(ValueError, match="buttons must not be empty"):
        meta_gateway_module._build_interactive_payload(
            WhatsAppInteractiveRequest(
                recipient="254700000031",
                interactive_type="button",
                body_text="Missing buttons",
            )
        )
    with pytest.raises(ValueError, match="sections must not be empty"):
        meta_gateway_module._build_interactive_payload(
            WhatsAppInteractiveRequest(
                recipient="254700000031",
                interactive_type="list",
                body_text="Missing sections",
                button_text="Choose",
            )
        )
    with pytest.raises(ValueError, match="rows must not be empty"):
        meta_gateway_module._build_interactive_section(
            WhatsAppInteractiveSection(rows=(), title="Empty")
        )
    assert _build_catalog_message_payload(
        WhatsAppCatalogMessageRequest(
            recipient="254700000031",
            body_text="Browse",
            footer_text="Footer copy",
            thumbnail_product_retailer_id="sku-1",
            provider_options={"biz_opaque_callback_data": "cb-catalog"},
        )
    )["interactive"]["action"] == {
        "name": "catalog_message",
        "parameters": {"thumbnail_product_retailer_id": "sku-1"},
    }
    assert _build_catalog_message_payload(
        WhatsAppCatalogMessageRequest(
            recipient="254700000031",
            body_text="Browse",
            footer_text="Footer copy",
        )
    )["interactive"]["footer"] == {"text": "Footer copy"}
    assert _build_product_message_payload(
        WhatsAppProductMessageRequest(
            recipient="254700000031",
            catalog_id="catalog-1",
            product_retailer_id="sku-1",
        )
    )["interactive"]["action"] == {
        "catalog_id": "catalog-1",
        "product_retailer_id": "sku-1",
    }
    assert _build_product_list_payload(
        WhatsAppProductListRequest(
            recipient="254700000031",
            catalog_id="catalog-1",
            header=WhatsAppInteractiveHeader(type="text", text="Store"),
            sections=(
                WhatsAppProductSection(
                    title="Popular",
                    product_items=(WhatsAppProductItem(product_retailer_id="sku-1"),),
                ),
            ),
        )
    )["interactive"]["action"]["sections"] == [
        {
            "title": "Popular",
            "product_items": [{"product_retailer_id": "sku-1"}],
        }
    ]
    assert _build_flow_message_payload(
        WhatsAppFlowMessageRequest(
            recipient="254700000031",
            flow_name="lead_capture",
            flow_cta="Open flow",
            flow_action_payload={"screen": "DETAILS"},
        )
    )["interactive"]["action"] == {
        "name": "flow",
        "parameters": {
            "flow_message_version": "3",
            "flow_name": "lead_capture",
            "flow_cta": "Open flow",
            "flow_action": "navigate",
            "flow_action_payload": {"screen": "DETAILS"},
        },
    }
    assert _build_media_upload_form(
        WhatsAppMediaUploadRequest(
            filename="poster.png",
            content=b"poster",
            mime_type="image/png",
            provider_options={"biz_opaque_callback_data": "cb-media"},
        )
    ) == {
        "biz_opaque_callback_data": "cb-media",
        "messaging_product": "whatsapp",
        "type": "image/png",
    }
    assert _build_media_upload_files(
        WhatsAppMediaUploadRequest(
            filename="poster.png",
            content=memoryview(b"poster"),
            mime_type="image/png",
        )
    ) == {"file": ("poster.png", b"poster", "image/png")}
    assert _build_media_upload_result("meta", {"id": "media-1"}).media_id == "media-1"
    assert _build_media_info("meta", "media-1", {"file_size": "12"}).file_size == 12
    assert _build_media_delete_result("meta", "media-1", {"success": 1}).deleted is True
    assert _build_template_list_query(None) is None
    assert _build_template_list_query(
        WhatsAppTemplateListRequest(
            category=("marketing", "utility"),
            content="hello",
            language=("en_US",),
            name="shipment_update",
            name_or_content="shipment",
            quality_score=("green",),
            since=10,
            status=("approved", "paused"),
            until=20,
            fields=("name", "category"),
            summary_fields=("total_count", "message_template_limit"),
            limit=25,
            before="prev-1",
            after="next-1",
            provider_options={"view": "full"},
        )
    ) == {
        "view": "full",
        "category": "MARKETING,UTILITY",
        "content": "hello",
        "language": "en_US",
        "name": "shipment_update",
        "name_or_content": "shipment",
        "quality_score": "GREEN",
        "since": "10",
        "status": "APPROVED,PAUSED",
        "until": "20",
        "fields": "name,category",
        "summary": "total_count,message_template_limit",
        "limit": "25",
        "before": "prev-1",
        "after": "next-1",
    }
    assert _build_template_fields_query(("name", "status")) == {"fields": "name,status"}
    assert _build_template_fields_query(()) is None
    assert _build_template_button_definition(
        WhatsAppTemplateButtonDefinition(
            type="flow",
            text="Open flow",
            flow_id="flow-1",
            flow_action="navigate",
            navigate_screen="SCREEN_A",
            supported_apps=({"package_name": "com.whatsapp", "signature_hash": "abc"},),
            provider_options={"index": 0},
        )
        ) == {
            "index": 0,
            "type": "FLOW",
            "text": "Open flow",
            "flow_id": "flow-1",
        "flow_action": "NAVIGATE",
            "navigate_screen": "SCREEN_A",
            "supported_apps": [{"package_name": "com.whatsapp", "signature_hash": "abc"}],
        }
    assert _build_template_button_definition(
        WhatsAppTemplateButtonDefinition(
            type="otp",
            phone_number="+254700000031",
            url="https://example.com/verify",
            example=("123456",),
            flow_name="flow-name",
            flow_json="{\"screen\":\"OTP\"}",
            otp_type="copy_code",
            zero_tap_terms_accepted=True,
        )
    ) == {
        "type": "OTP",
        "phone_number": "+254700000031",
        "url": "https://example.com/verify",
        "example": ["123456"],
        "flow_name": "flow-name",
        "flow_json": "{\"screen\":\"OTP\"}",
        "otp_type": "COPY_CODE",
        "zero_tap_terms_accepted": True,
    }
    assert _build_template_component_definition(
        WhatsAppTemplateComponentDefinition(
            type="buttons",
            buttons=(
                WhatsAppTemplateButtonDefinition(type="quick_reply", text="Track"),
            ),
            example={"header_text": ["Track package"]},
            provider_options={"add_security_recommendation": True},
        )
    ) == {
        "add_security_recommendation": True,
        "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": "Track"}],
            "example": {"header_text": ["Track package"]},
        }
    assert _build_template_component_definition(
        WhatsAppTemplateComponentDefinition(
            type="header",
            format="text",
            text="Header",
        )
    ) == {
        "type": "HEADER",
        "format": "TEXT",
        "text": "Header",
    }
    assert _build_template_create_payload(
        WhatsAppTemplateCreateRequest(
            name="shipment_update",
            language="en_US",
            category="utility",
            components=(
                WhatsAppTemplateComponentDefinition(type="body", text="Hello {{1}}"),
            ),
            allow_category_change=True,
            parameter_format="positional",
            sub_category="custom",
            message_send_ttl_seconds=600,
            library_template_name="shipment_library",
            is_primary_device_delivery_only=False,
            creative_sourcing_spec={"source": "LIBRARY"},
            library_template_body_inputs={"name": "Alice"},
            library_template_button_inputs=({"code": "TRACK"},),
            provider_options={"add_security_recommendation": True},
        )
    ) == {
        "add_security_recommendation": True,
        "name": "shipment_update",
        "language": "en_US",
        "category": "UTILITY",
        "allow_category_change": True,
        "components": [{"type": "BODY", "text": "Hello {{1}}"}],
        "parameter_format": "POSITIONAL",
        "sub_category": "CUSTOM",
        "message_send_ttl_seconds": 600,
        "library_template_name": "shipment_library",
        "is_primary_device_delivery_only": False,
        "creative_sourcing_spec": {"source": "LIBRARY"},
        "library_template_body_inputs": {"name": "Alice"},
        "library_template_button_inputs": [{"code": "TRACK"}],
    }
    assert _build_template_update_payload(
        WhatsAppTemplateUpdateRequest(
            category="marketing",
            components=(
                WhatsAppTemplateComponentDefinition(type="body", text="Updated {{1}}"),
            ),
            parameter_format="positional",
            message_send_ttl_seconds=300,
            creative_sourcing_spec={"source": "USER"},
            provider_options={"allow_category_change": True},
        )
    ) == {
        "allow_category_change": True,
        "category": "MARKETING",
        "components": [{"type": "BODY", "text": "Updated {{1}}"}],
        "parameter_format": "POSITIONAL",
        "message_send_ttl_seconds": 300,
        "creative_sourcing_spec": {"source": "USER"},
    }
    assert _build_template_delete_query(
        WhatsAppTemplateDeleteRequest(name="shipment_update", template_id="tmpl-1")
    ) == {"name": "shipment_update", "hsm_id": "tmpl-1"}
    assert _build_template_delete_query(
        WhatsAppTemplateDeleteRequest(template_ids="tmpl-1")
    ) == {"hsm_ids": '["tmpl-1"]'}
    assert _build_template_delete_query(
        WhatsAppTemplateDeleteRequest(template_ids=("tmpl-1", "tmpl-2"))
    ) == {"hsm_ids": '["tmpl-1", "tmpl-2"]'}
    managed_template = _build_managed_template(
        "meta",
        {
            "id": "tmpl-1",
            "name": "shipment_update",
            "language": "en_US",
            "category": "UTILITY",
            "status": "APPROVED",
            "components": [
                {"type": "BODY", "text": "Hello {{1}}"},
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {
                            "type": "FLOW",
                            "text": "Track",
                            "flow_id": "flow-1",
                            "flow_action": "NAVIGATE",
                            "navigate_screen": "SCREEN_A",
                        }
                    ],
                },
            ],
            "parameter_format": "POSITIONAL",
            "quality_score": {"score": "GREEN"},
            "cta_url_link_tracking_opted_out": True,
            "message_send_ttl_seconds": "600",
            "bid_spec": {"bid": "default"},
        },
    )
    assert managed_template.template_id == "tmpl-1"
    assert managed_template.quality_score == "GREEN"
    assert managed_template.cta_url_link_tracking_opted_out is True
    assert managed_template.components[1].buttons[0].flow_action == "NAVIGATE"
    assert managed_template.metadata == {
        "bid_spec": {"bid": "default"},
        "quality_score_details": {"score": "GREEN"},
    }
    listed_templates = _build_template_list_result(
        "meta",
        {
            "data": [
                {
                    "id": "tmpl-1",
                    "name": "shipment_update",
                    "language": "en_US",
                    "category": "UTILITY",
                    "status": "APPROVED",
                }
            ],
            "paging": {"cursors": {"before": "prev-1", "after": "next-1"}},
            "summary": {
                "total_count": "1",
                "message_template_count": "1",
                "message_template_limit": "250",
                "are_translations_complete": True,
            },
        },
    )
    assert listed_templates.before == "prev-1"
    assert listed_templates.after == "next-1"
    assert listed_templates.summary == WhatsAppTemplateListSummary(
        total_count=1,
        message_template_count=1,
        message_template_limit=250,
        are_translations_complete=True,
        raw={
            "total_count": "1",
            "message_template_count": "1",
            "message_template_limit": "250",
            "are_translations_complete": True,
        },
    )
    assert _build_template_mutation_result("meta", {"id": "tmpl-1"}).success is True
    assert _build_template_mutation_result(
        "meta",
        {"success": False},
        fallback_template_id="tmpl-fallback",
    ).template_id == "tmpl-fallback"
    query: dict[str, str] = {}
    meta_gateway_module._set_query_value(query, "ratio", 2.5)
    assert query == {"ratio": "2.5"}
    assert _build_template_delete_result(
        "meta",
        WhatsAppTemplateDeleteRequest(template_ids=("tmpl-1", "tmpl-2")),
        {"success": True},
    ) == WhatsAppTemplateDeleteResult(
        provider="meta",
        deleted=True,
        name=None,
        template_id=None,
        template_ids=("tmpl-1", "tmpl-2"),
        raw={"success": True},
    )
    with pytest.raises(ValueError, match="header is required"):
        _build_product_list_payload(
            WhatsAppProductListRequest(
                recipient="254700000031",
                catalog_id="catalog-1",
                header=None,  # type: ignore[arg-type]
                sections=(
                    WhatsAppProductSection(
                        title="Popular",
                        product_items=(WhatsAppProductItem(product_retailer_id="sku-1"),),
                    ),
                ),
            )
        )
    with pytest.raises(ValueError, match="sections must not be empty"):
        _build_product_list_payload(
            WhatsAppProductListRequest(
                recipient="254700000031",
                catalog_id="catalog-1",
                header=WhatsAppInteractiveHeader(type="text", text="Store"),
                sections=(),
            )
        )
    with pytest.raises(ValueError, match="sections\\[\\]\\.product_items must not be empty"):
        _build_product_list_payload(
            WhatsAppProductListRequest(
                recipient="254700000031",
                catalog_id="catalog-1",
                header=WhatsAppInteractiveHeader(type="text", text="Store"),
                sections=(WhatsAppProductSection(title="Popular", product_items=()),),
            )
        )
    with pytest.raises(ValueError, match="exactly one of flow_id or flow_name"):
        _build_flow_message_payload(
            WhatsAppFlowMessageRequest(
                recipient="254700000031",
                flow_id="flow-1",
                flow_name="lead_capture",
                flow_cta="Open flow",
            )
        )
    with pytest.raises(ValueError, match="content must not be empty"):
        _build_media_upload_files(
            WhatsAppMediaUploadRequest(
                filename="poster.png",
                content=b"",
                mime_type="image/png",
            )
        )
    with pytest.raises(GatewayError, match="media id"):
        _build_media_upload_result("meta", {})
    with pytest.raises(ValueError, match="template update request must include at least one field"):
        _build_template_update_payload(WhatsAppTemplateUpdateRequest())
    with pytest.raises(ValueError, match="template_ids cannot be combined"):
        _build_template_delete_query(
            WhatsAppTemplateDeleteRequest(
                name="shipment_update",
                template_ids=("tmpl-1",),
            )
        )
    with pytest.raises(ValueError, match="requires name or template_ids"):
        _build_template_delete_query(WhatsAppTemplateDeleteRequest())
    with pytest.raises(GatewayError, match="template id"):
        _build_managed_template("meta", {"name": "missing-id"})

    assert (
        meta_gateway_module._build_inbound_message(
            provider_name="meta",
            payload={"from": "254700000031"},
            profiles={},
            webhook_metadata={},
        )
        is None
    )
    media_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000031",
            "id": "wamid.image-empty",
            "type": "image",
            "image": {},
        },
        profiles={},
        webhook_metadata={},
    )
    assert media_message is not None
    assert media_message.media is None
    location_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000031",
            "id": "wamid.location-empty",
            "type": "location",
            "location": {},
        },
        profiles={},
        webhook_metadata={},
    )
    assert location_message is not None
    assert location_message.location is None
    button_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000031",
            "id": "wamid.button-empty",
            "type": "button",
            "button": {},
        },
        profiles={},
        webhook_metadata={},
    )
    assert button_message is not None
    assert button_message.reply is None
    interactive_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000031",
            "id": "wamid.interactive-button",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "btn-1", "title": "Button 1"},
            },
        },
        profiles={},
        webhook_metadata={},
    )
    assert interactive_message is not None
    assert interactive_message.reply is not None
    assert interactive_message.reply.reply_type == "button_reply"
    unsupported_interactive_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000031",
            "id": "wamid.interactive-unsupported",
            "type": "interactive",
            "interactive": {"type": "nfm_reply"},
        },
        profiles={},
        webhook_metadata={},
    )
    assert unsupported_interactive_message is not None
    assert unsupported_interactive_message.reply is None
    reaction_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000031",
            "id": "wamid.reaction-empty",
            "type": "reaction",
            "reaction": {},
        },
        profiles={},
        webhook_metadata={},
    )
    assert reaction_message is not None
    assert reaction_message.reaction is None
    contacts_message = meta_gateway_module._build_inbound_message(
        provider_name="meta",
        payload={
            "from": "254700000032",
            "id": "wamid.contacts-full",
            "type": "contacts",
            "context": {
                "message_id": "wamid.parent",
                "forwarded": True,
                "frequently_forwarded": False,
            },
            "contacts": [
                {"name": {}},
                {
                    "name": {
                        "formatted_name": "Alice Example",
                        "first_name": "Alice",
                        "last_name": "Example",
                    },
                    "phones": [
                        {
                            "phone": "+254700000032",
                            "type": "CELL",
                            "wa_id": "254700000032",
                        }
                    ],
                    "emails": [{"email": "alice@example.com", "type": "WORK"}],
                    "urls": [{"url": "https://example.com", "type": "WORK"}],
                    "addresses": [
                        {
                            "street": "2 Example Road",
                            "city": "Nairobi",
                            "state": "Nairobi",
                            "zip": "00100",
                            "country": "Kenya",
                            "country_code": "KE",
                            "type": "HOME",
                        }
                    ],
                    "org": {
                        "company": "Noria",
                        "department": "Ops",
                        "title": "Manager",
                    },
                    "birthday": "1991-02-03",
                },
            ],
        },
        profiles={"254700000032": "Alice Profile"},
        webhook_metadata={
            "display_phone_number": "254700000099",
            "phone_number_id": "99999",
        },
    )
    assert contacts_message is not None
    assert contacts_message.profile_name == "Alice Profile"
    assert contacts_message.context_message_id == "wamid.parent"
    assert contacts_message.forwarded is True
    assert contacts_message.frequently_forwarded is False
    assert contacts_message.metadata == {
        "display_phone_number": "254700000099",
        "phone_number_id": "99999",
    }
    assert len(contacts_message.contacts) == 1
    assert contacts_message.contacts[0].emails[0].email == "alice@example.com"
    assert contacts_message.contacts[0].urls[0].url == "https://example.com"
    assert contacts_message.contacts[0].addresses[0].country_code == "KE"
    assert contacts_message.contacts[0].org is not None
    assert contacts_message.contacts[0].org.company == "Noria"
    assert contacts_message.contacts[0].birthday == "1991-02-03"

    assert meta_gateway_module._coerce_float(5) == 5.0
    assert meta_gateway_module._coerce_float(None) is None
    assert meta_gateway_module._coerce_float("not-a-number") is None
    assert meta_gateway_module._coerce_int("12") == 12
    assert meta_gateway_module._coerce_int(9) == 9
    assert meta_gateway_module._coerce_int(None) is None
    assert meta_gateway_module._coerce_int("bad-int") is None
    assert meta_gateway_module._coerce_int(True) is None


def test_webhook_helpers_cover_fastapi_flask_and_onfon_paths() -> None:
    sms_gateway = OnfonSmsGateway(access_key="a", api_key="b", client_id="c")
    whatsapp_gateway = MetaWhatsAppGateway(
        access_token="meta-token",
        phone_number_id="123456789",
        app_secret="app-secret",
    )

    assert fastapi_resolve_meta_subscription_challenge(
        FakeFastAPIRequest(
            query_params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "1234",
            }
        ),
        "verify-me",
    ) == "1234"
    assert flask_resolve_meta_subscription_challenge(
        FakeFlaskRequest(
            args={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "5678",
            }
        ),
        "verify-me",
    ) == "5678"

    assert asyncio.run(
        fastapi_parse_onfon_delivery_report(
            FakeFastAPIRequest(query_params={"messageId": "sms-fastapi-1"}),
            sms_gateway,
        )
    ).provider_message_id == "sms-fastapi-1"
    assert flask_parse_onfon_delivery_report(
        FakeFlaskRequest(args={"messageId": "sms-flask-1"}),
        sms_gateway,
    ).provider_message_id == "sms-flask-1"
    assert (
        parse_onfon_delivery_report(
            {"messageId": "sms-helper-1"},
            sms_gateway,
        ).provider_message_id
        == "sms-helper-1"
    )

    payload = b"[]"
    signature = hmac.new(b"app-secret", payload, hashlib.sha256).hexdigest()
    assert (
        asyncio.run(
            fastapi_parse_meta_delivery_events(
                FakeFastAPIRequest(
                    headers={"x-hub-signature-256": f"sha256={signature}"},
                    payload=payload,
                ),
                whatsapp_gateway,
                require_signature=True,
            )
        )
        == ()
    )
    assert (
        asyncio.run(
            fastapi_parse_meta_inbound_messages(
                FakeFastAPIRequest(payload=payload),
                whatsapp_gateway,
            )
        )
        == ()
    )
    assert flask_parse_meta_delivery_events(
        FakeFlaskRequest(
            json_payload={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "statuses": [
                                        {
                                            "id": "wamid.webhook.1",
                                            "status": "delivered",
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
        ),
        whatsapp_gateway,
    )[0].provider_message_id == "wamid.webhook.1"
    assert (
        flask_parse_meta_delivery_events(
            FakeFlaskRequest(
                headers={"X-Hub-Signature-256": f"sha256={signature}"},
                payload=payload,
                json_payload=["not-a-dict"],
            ),
            whatsapp_gateway,
            require_signature=True,
        )
        == ()
    )
    assert (
        flask_parse_meta_inbound_messages(
            FakeFlaskRequest(
                json_payload=["not-a-dict"],
            ),
            whatsapp_gateway,
        )
        == ()
    )


def test_parse_decimal_handles_invalid_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_decimal(value: str) -> Decimal:
        raise InvalidOperation

    monkeypatch.setattr("noriacomm.utils.Decimal", broken_decimal)
    assert parse_decimal_from_text("123.45") is None
