from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from ....events import DeliveryEvent
from ....exceptions import ConfigurationError, GatewayError
from ....http import AsyncHttpClient, HttpClient
from ....types import Hooks, HttpRequestOptions, RequestOptions, RetryPolicy
from ....utils import coerce_string, merge_headers, to_object
from ..models import (
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
    WhatsAppInboundLocation,
    WhatsAppInboundMedia,
    WhatsAppInboundMessage,
    WhatsAppInboundReaction,
    WhatsAppInboundReply,
    WhatsAppInteractiveButton,
    WhatsAppInteractiveHeader,
    WhatsAppInteractiveRequest,
    WhatsAppInteractiveRow,
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

META_GRAPH_BASE_URL = "https://graph.facebook.com"
META_GRAPH_API_VERSION = "v25.0"
_MEDIA_TYPES = {"image", "audio", "document", "sticker", "video"}


@dataclass(slots=True)
class MetaWhatsAppGateway:
    access_token: str
    phone_number_id: str
    whatsapp_business_account_id: str | None = None
    app_secret: str | None = None
    webhook_verify_token: str | None = None
    api_version: str = META_GRAPH_API_VERSION
    base_url: str = META_GRAPH_BASE_URL
    client: httpx.Client | Any | None = None
    async_client: httpx.AsyncClient | Any | None = None
    timeout_seconds: float | None = 30.0
    default_headers: Mapping[str, str] | None = None
    retry: RetryPolicy | None = None
    hooks: Hooks | None = None
    provider_name: str = field(init=False, default="meta")
    _transport_headers: dict[str, str] = field(init=False, repr=False)
    _http: HttpClient | None = field(init=False, repr=False, default=None)
    _async_http: AsyncHttpClient | None = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self.access_token = _require_text(self.access_token, "access_token")
        self.phone_number_id = _require_text(self.phone_number_id, "phone_number_id")
        self.whatsapp_business_account_id = coerce_string(self.whatsapp_business_account_id)
        self.app_secret = coerce_string(self.app_secret)
        self.webhook_verify_token = coerce_string(self.webhook_verify_token)
        self.api_version = _require_text(self.api_version, "api_version")
        self._transport_headers = merge_headers(
            self.default_headers,
            {
                "Authorization": f"Bearer {self.access_token}",
            },
        )

    def send_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_text_payload(request),
            options=options,
        )

    async def asend_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_text_payload(request),
            options=options,
        )

    def send_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_template_payload(request),
            options=options,
        )

    async def asend_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_template_payload(request),
            options=options,
        )

    def list_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        response = self._request(
            HttpRequestOptions(
                path=self._template_collection_path(),
                method="GET",
                query=_build_template_list_query(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_list_result(self.provider_name, response)

    async def alist_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._template_collection_path(),
                method="GET",
                query=_build_template_list_query(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_list_result(self.provider_name, response)

    def get_template(
        self,
        template_id: str,
        *,
        fields: Sequence[str] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        response = self._request(
            HttpRequestOptions(
                path=self._template_path(template_id),
                method="GET",
                query=_build_template_fields_query(fields),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_managed_template(self.provider_name, response)

    async def aget_template(
        self,
        template_id: str,
        *,
        fields: Sequence[str] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._template_path(template_id),
                method="GET",
                query=_build_template_fields_query(fields),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_managed_template(self.provider_name, response)

    def create_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        response = self._request(
            HttpRequestOptions(
                path=self._template_collection_path(),
                method="POST",
                body=_build_template_create_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_mutation_result(self.provider_name, response)

    async def acreate_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._template_collection_path(),
                method="POST",
                body=_build_template_create_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_mutation_result(self.provider_name, response)

    def update_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        response = self._request(
            HttpRequestOptions(
                path=self._template_path(template_id),
                method="POST",
                body=_build_template_update_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_mutation_result(
            self.provider_name,
            response,
            fallback_template_id=_require_text(template_id, "template_id"),
        )

    async def aupdate_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._template_path(template_id),
                method="POST",
                body=_build_template_update_payload(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_mutation_result(
            self.provider_name,
            response,
            fallback_template_id=_require_text(template_id, "template_id"),
        )

    def delete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult:
        response = self._request(
            HttpRequestOptions(
                path=self._template_collection_path(),
                method="DELETE",
                query=_build_template_delete_query(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_delete_result(self.provider_name, request, response)

    async def adelete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._template_collection_path(),
                method="DELETE",
                query=_build_template_delete_query(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_template_delete_result(self.provider_name, request, response)

    def send_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_media_payload(request),
            options=options,
        )

    async def asend_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_media_payload(request),
            options=options,
        )

    def send_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_location_payload(request),
            options=options,
        )

    async def asend_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_location_payload(request),
            options=options,
        )

    def send_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_contacts_payload(request),
            options=options,
        )

    async def asend_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_contacts_payload(request),
            options=options,
        )

    def send_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_reaction_payload(request),
            options=options,
        )

    async def asend_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_reaction_payload(request),
            options=options,
        )

    def send_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_interactive_payload(request),
            options=options,
        )

    async def asend_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_interactive_payload(request),
            options=options,
        )

    def send_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_catalog_message_payload(request),
            options=options,
        )

    async def asend_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_catalog_message_payload(request),
            options=options,
        )

    def send_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_product_message_payload(request),
            options=options,
        )

    async def asend_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_product_message_payload(request),
            options=options,
        )

    def send_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_product_list_payload(request),
            options=options,
        )

    async def asend_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_product_list_payload(request),
            options=options,
        )

    def send_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return self._send_request(
            request.recipient,
            _build_flow_message_payload(request),
            options=options,
        )

    async def asend_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await self._asend_request(
            request.recipient,
            _build_flow_message_payload(request),
            options=options,
        )

    def upload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult:
        response = self._request(
            HttpRequestOptions(
                path=self._media_upload_path(),
                method="POST",
                form=_build_media_upload_form(request),
                files=_build_media_upload_files(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_media_upload_result(self.provider_name, response)

    async def aupload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._media_upload_path(),
                method="POST",
                form=_build_media_upload_form(request),
                files=_build_media_upload_files(request),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_media_upload_result(self.provider_name, response)

    def get_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo:
        response = self._request(
            HttpRequestOptions(
                path=self._media_path(media_id),
                method="GET",
                query=self._media_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_media_info(self.provider_name, media_id, response)

    async def aget_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._media_path(media_id),
                method="GET",
                query=self._media_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_media_info(self.provider_name, media_id, response)

    def delete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult:
        response = self._request(
            HttpRequestOptions(
                path=self._media_path(media_id),
                method="DELETE",
                query=self._media_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_media_delete_result(self.provider_name, media_id, response)

    async def adelete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._media_path(media_id),
                method="DELETE",
                query=self._media_query(),
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return _build_media_delete_result(self.provider_name, media_id, response)

    def parse_events(self, payload: Mapping[str, object]) -> tuple[DeliveryEvent, ...]:
        events: list[DeliveryEvent] = []

        for value in _iterate_value_objects(payload):
            statuses = value.get("statuses")
            if not isinstance(statuses, list):
                continue

            for row in statuses:
                event = self._build_status_event(row)
                if event is not None:
                    events.append(event)

        return tuple(events)

    def parse_event(self, payload: Mapping[str, object]) -> DeliveryEvent | None:
        events = self.parse_events(payload)
        return events[0] if events else None

    def parse_inbound_messages(
        self,
        payload: Mapping[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]:
        messages: list[WhatsAppInboundMessage] = []

        for value in _iterate_value_objects(payload):
            inbound_rows = value.get("messages")
            if not isinstance(inbound_rows, list):
                continue

            profiles = _build_profile_lookup(value.get("contacts"))
            metadata = to_object(value.get("metadata"))
            for row in inbound_rows:
                message = _build_inbound_message(
                    provider_name=self.provider_name,
                    payload=row,
                    profiles=profiles,
                    webhook_metadata=metadata,
                )
                if message is not None:
                    messages.append(message)

        return tuple(messages)

    def parse_inbound_message(self, payload: Mapping[str, object]) -> WhatsAppInboundMessage | None:
        messages = self.parse_inbound_messages(payload)
        return messages[0] if messages else None

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    async def aclose(self) -> None:
        if self._async_http is not None:
            await self._async_http.aclose()

    def _messages_path(self) -> str:
        return f"/{self.api_version}/{self.phone_number_id}/messages"

    def _template_collection_path(self) -> str:
        return (
            f"/{self.api_version}/{self._require_whatsapp_business_account_id()}/message_templates"
        )

    def _template_path(self, template_id: str) -> str:
        return f"/{self.api_version}/{_require_text(template_id, 'template_id')}"

    def _media_upload_path(self) -> str:
        return f"/{self.api_version}/{self.phone_number_id}/media"

    def _media_path(self, media_id: str) -> str:
        return f"/{self.api_version}/{_require_text(media_id, 'media_id')}"

    def _media_query(self) -> dict[str, str]:
        return {"phone_number_id": self.phone_number_id}

    def _require_whatsapp_business_account_id(self) -> str:
        if self.whatsapp_business_account_id is None:
            raise ConfigurationError(
                "Meta WhatsApp template management requires whatsapp_business_account_id."
            )
        return self.whatsapp_business_account_id

    def _send_request(
        self,
        recipient: str,
        payload: Mapping[str, object],
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        response = self._request(
            HttpRequestOptions(
                path=self._messages_path(),
                method="POST",
                body=payload,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_send_result(recipient, response)

    async def _asend_request(
        self,
        recipient: str,
        payload: Mapping[str, object],
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        response = await self._arequest(
            HttpRequestOptions(
                path=self._messages_path(),
                method="POST",
                body=payload,
                headers=options.headers if options else None,
                timeout_seconds=options.timeout_seconds if options else None,
                retry=options.retry if options else None,
            )
        )
        return self._build_send_result(recipient, response)

    def _build_status_event(self, payload: object) -> DeliveryEvent | None:
        status = to_object(payload)
        provider_message_id = coerce_string(status.get("id"))
        if provider_message_id is None:
            return None

        error = _first_mapping(status.get("errors"))
        conversation = to_object(status.get("conversation"))
        pricing = to_object(status.get("pricing"))
        provider_status = coerce_string(status.get("status"))
        return DeliveryEvent(
            channel="whatsapp",
            provider=self.provider_name,
            provider_message_id=provider_message_id,
            state=_map_whatsapp_state(provider_status),
            recipient=coerce_string(status.get("recipient_id")),
            provider_status=provider_status,
            error_code=coerce_string(error.get("code")),
            error_description=(
                coerce_string(error.get("message"))
                or coerce_string(error.get("title"))
                or coerce_string(error.get("details"))
            ),
            occurred_at=coerce_string(status.get("timestamp")),
            metadata={
                "conversation_id": coerce_string(conversation.get("id")),
                "conversation_origin_type": coerce_string(
                    to_object(conversation.get("origin")).get("type")
                ),
                "pricing_model": coerce_string(pricing.get("pricing_model")),
                "billable": pricing.get("billable"),
                "category": coerce_string(pricing.get("category")),
            },
            raw=status,
        )

    def _build_send_result(
        self,
        recipient: str,
        response: Mapping[str, object],
    ) -> WhatsAppSendResult:
        contacts = response.get("contacts")
        messages = response.get("messages")
        items = messages if isinstance(messages, list) else []
        contact = _first_mapping(contacts)
        message = _first_mapping(items)
        provider_message_id = coerce_string(message.get("id"))
        provider_status = coerce_string(message.get("message_status"))

        if provider_message_id is None:
            raise GatewayError(
                "Meta WhatsApp Cloud API did not return a message id.",
                provider=self.provider_name,
                response_body=response,
            )

        receipt = WhatsAppSendReceipt(
            provider=self.provider_name,
            recipient=coerce_string(contact.get("wa_id")) or recipient,
            status="submitted",
            provider_message_id=provider_message_id,
            provider_status=provider_status,
            raw=message or response,
        )
        return WhatsAppSendResult(
            provider=self.provider_name,
            accepted=True,
            error_code=None,
            error_description=None,
            messages=(receipt,),
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
                "Meta WhatsApp Cloud API returned a non-object response.",
                provider=self.provider_name,
                response_body=response,
            )

        error = to_object(payload.get("error"))
        if error:
            description = (
                coerce_string(error.get("error_user_msg"))
                or coerce_string(error.get("message"))
                or "Provider request failed."
            )
            raise GatewayError(
                f"Meta WhatsApp request failed: {description}",
                provider=self.provider_name,
                error_code=coerce_string(error.get("code")),
                error_description=description,
                response_body=payload,
            )

        return payload


def _build_media_upload_result(
    provider_name: str,
    response: Mapping[str, object],
) -> WhatsAppMediaUploadResult:
    media_id = coerce_string(response.get("id"))
    if media_id is None:
        raise GatewayError(
            "Meta media upload did not return a media id.",
            provider=provider_name,
            response_body=response,
        )
    return WhatsAppMediaUploadResult(
        provider=provider_name,
        media_id=media_id,
        raw=response,
    )


def _build_media_info(
    provider_name: str,
    media_id: str,
    response: Mapping[str, object],
) -> WhatsAppMediaInfo:
    return WhatsAppMediaInfo(
        provider=provider_name,
        media_id=coerce_string(response.get("id")) or media_id,
        url=coerce_string(response.get("url")),
        mime_type=coerce_string(response.get("mime_type")),
        sha256=coerce_string(response.get("sha256")),
        file_size=_coerce_int(response.get("file_size")),
        raw=response,
    )


def _build_media_delete_result(
    provider_name: str,
    media_id: str,
    response: Mapping[str, object],
) -> WhatsAppMediaDeleteResult:
    return WhatsAppMediaDeleteResult(
        provider=provider_name,
        media_id=media_id,
        deleted=bool(response.get("success")),
        raw=response,
    )


def _build_template_list_query(
    request: WhatsAppTemplateListRequest | None,
) -> dict[str, str] | None:
    if request is None:
        return None

    query: dict[str, str] = {
        key: _require_text(coerce_string(value), f"provider_options[{key}]")
        for key, value in request.provider_options.items()
    }
    _set_query_value(query, "category", request.category, uppercase=True)
    _set_query_value(query, "content", request.content)
    _set_query_value(query, "language", request.language)
    _set_query_value(query, "name", request.name)
    _set_query_value(query, "name_or_content", request.name_or_content)
    _set_query_value(query, "quality_score", request.quality_score, uppercase=True)
    _set_query_value(query, "since", request.since)
    _set_query_value(query, "status", request.status, uppercase=True)
    _set_query_value(query, "until", request.until)
    _set_query_value(query, "fields", request.fields)
    _set_query_value(query, "summary", request.summary_fields)
    _set_query_value(query, "limit", request.limit)
    _set_query_value(query, "before", request.before)
    _set_query_value(query, "after", request.after)
    return query or None


def _build_template_fields_query(fields: Sequence[str]) -> dict[str, str] | None:
    query: dict[str, str] = {}
    _set_query_value(query, "fields", fields)
    return query or None


def _build_template_create_payload(request: WhatsAppTemplateCreateRequest) -> dict[str, Any]:
    payload = dict(request.provider_options or {})
    payload["name"] = _require_text(request.name, "name")
    payload["language"] = _require_text(request.language, "language")
    payload["category"] = _normalize_template_enum(request.category, "category")
    if request.allow_category_change is not None:
        payload["allow_category_change"] = request.allow_category_change
    if request.components:
        payload["components"] = [
            _build_template_component_definition(component) for component in request.components
        ]
    if request.parameter_format is not None:
        payload["parameter_format"] = _normalize_template_enum(
            request.parameter_format,
            "parameter_format",
        )
    if request.sub_category is not None:
        payload["sub_category"] = _normalize_template_enum(request.sub_category, "sub_category")
    if request.message_send_ttl_seconds is not None:
        payload["message_send_ttl_seconds"] = request.message_send_ttl_seconds
    if request.library_template_name is not None:
        payload["library_template_name"] = _require_text(
            request.library_template_name,
            "library_template_name",
        )
    if request.is_primary_device_delivery_only is not None:
        payload["is_primary_device_delivery_only"] = request.is_primary_device_delivery_only
    if request.creative_sourcing_spec:
        payload["creative_sourcing_spec"] = dict(request.creative_sourcing_spec)
    if request.library_template_body_inputs:
        payload["library_template_body_inputs"] = dict(request.library_template_body_inputs)
    if request.library_template_button_inputs:
        payload["library_template_button_inputs"] = [
            dict(item) for item in request.library_template_button_inputs
        ]
    return payload


def _build_template_update_payload(request: WhatsAppTemplateUpdateRequest) -> dict[str, Any]:
    payload = dict(request.provider_options or {})
    if request.category is not None:
        payload["category"] = _normalize_template_enum(request.category, "category")
    if request.components:
        payload["components"] = [
            _build_template_component_definition(component) for component in request.components
        ]
    if request.parameter_format is not None:
        payload["parameter_format"] = _normalize_template_enum(
            request.parameter_format,
            "parameter_format",
        )
    if request.message_send_ttl_seconds is not None:
        payload["message_send_ttl_seconds"] = request.message_send_ttl_seconds
    if request.creative_sourcing_spec:
        payload["creative_sourcing_spec"] = dict(request.creative_sourcing_spec)
    if not payload:
        raise ValueError("template update request must include at least one field.")
    return payload


def _build_template_delete_query(request: WhatsAppTemplateDeleteRequest) -> dict[str, str]:
    query: dict[str, str] = {
        key: _require_text(coerce_string(value), f"provider_options[{key}]")
        for key, value in request.provider_options.items()
    }
    template_ids = _normalize_text_sequence(request.template_ids, "template_ids[]")
    template_id = coerce_string(request.template_id)
    name = coerce_string(request.name)

    if template_ids:
        if name is not None or template_id is not None:
            raise ValueError("template_ids cannot be combined with name or template_id.")
        query["hsm_ids"] = json.dumps(list(template_ids))
        return query

    if name is None:
        raise ValueError("delete template request requires name or template_ids.")
    query["name"] = _require_text(name, "name")
    if template_id is not None:
        query["hsm_id"] = _require_text(template_id, "template_id")
    return query


def _build_template_component_definition(
    component: WhatsAppTemplateComponentDefinition,
) -> dict[str, Any]:
    payload = dict(component.provider_options or {})
    payload["type"] = _normalize_template_enum(component.type, "components[].type")
    if component.format is not None:
        payload["format"] = _normalize_template_enum(component.format, "components[].format")
    if component.text is not None:
        payload["text"] = component.text
    if component.buttons:
        payload["buttons"] = [
            _build_template_button_definition(button) for button in component.buttons
        ]
    if component.example:
        payload["example"] = dict(component.example)
    return payload


def _build_template_button_definition(
    button: WhatsAppTemplateButtonDefinition,
) -> dict[str, Any]:
    payload = dict(button.provider_options or {})
    payload["type"] = _normalize_template_enum(button.type, "buttons[].type")
    if button.text is not None:
        payload["text"] = button.text
    if button.phone_number is not None:
        payload["phone_number"] = button.phone_number
    if button.url is not None:
        payload["url"] = button.url
    if button.example:
        payload["example"] = list(button.example)
    if button.flow_id is not None:
        payload["flow_id"] = button.flow_id
    if button.flow_name is not None:
        payload["flow_name"] = button.flow_name
    if button.flow_json is not None:
        payload["flow_json"] = button.flow_json
    if button.flow_action is not None:
        payload["flow_action"] = _normalize_template_enum(
            button.flow_action,
            "buttons[].flow_action",
        )
    if button.navigate_screen is not None:
        payload["navigate_screen"] = button.navigate_screen
    if button.otp_type is not None:
        payload["otp_type"] = _normalize_template_enum(button.otp_type, "buttons[].otp_type")
    if button.zero_tap_terms_accepted is not None:
        payload["zero_tap_terms_accepted"] = button.zero_tap_terms_accepted
    if button.supported_apps:
        payload["supported_apps"] = [dict(item) for item in button.supported_apps]
    return payload


def _build_template_list_result(
    provider_name: str,
    response: Mapping[str, object],
) -> WhatsAppTemplateListResult:
    rows = response.get("data")
    templates = tuple(
        _build_managed_template(provider_name, row)
        for row in (rows if isinstance(rows, list) else [])
    )
    paging = to_object(response.get("paging"))
    cursors = to_object(paging.get("cursors"))
    summary_payload = to_object(response.get("summary"))
    return WhatsAppTemplateListResult(
        provider=provider_name,
        templates=templates,
        before=coerce_string(cursors.get("before")),
        after=coerce_string(cursors.get("after")),
        summary=(
            _build_template_list_summary(summary_payload) if summary_payload else None
        ),
        raw=response,
    )


def _build_template_list_summary(
    payload: Mapping[str, object],
) -> WhatsAppTemplateListSummary:
    return WhatsAppTemplateListSummary(
        total_count=_coerce_int(payload.get("total_count")),
        message_template_count=_coerce_int(payload.get("message_template_count")),
        message_template_limit=_coerce_int(payload.get("message_template_limit")),
        are_translations_complete=_coerce_bool(payload.get("are_translations_complete")),
        raw=payload,
    )


def _build_managed_template(
    provider_name: str,
    payload: object,
) -> WhatsAppManagedTemplate:
    row = to_object(payload)
    template_id = coerce_string(row.get("id"))
    if template_id is None:
        raise GatewayError(
            "Meta template response did not include a template id.",
            provider=provider_name,
            response_body=payload,
        )

    components = tuple(
        _parse_template_component_definition(item)
        for item in _normalize_rows(row.get("components"))
    )
    quality_payload = to_object(row.get("quality_score"))
    metadata = _compact_mapping(
        {
            "bid_spec": to_object(row.get("bid_spec")) or None,
            "degrees_of_freedom_spec": to_object(row.get("degrees_of_freedom_spec")) or None,
            "quality_score_details": quality_payload or None,
        }
    )
    return WhatsAppManagedTemplate(
        provider=provider_name,
        template_id=template_id,
        name=coerce_string(row.get("name")),
        language=coerce_string(row.get("language")),
        category=coerce_string(row.get("category")),
        status=coerce_string(row.get("status")),
        components=components,
        parameter_format=coerce_string(row.get("parameter_format")),
        sub_category=coerce_string(row.get("sub_category")),
        previous_category=coerce_string(row.get("previous_category")),
        correct_category=coerce_string(row.get("correct_category")),
        rejected_reason=coerce_string(row.get("rejected_reason")),
        quality_score=(
            coerce_string(quality_payload.get("score"))
            or coerce_string(quality_payload.get("quality_score"))
            or coerce_string(row.get("quality_score"))
        ),
        cta_url_link_tracking_opted_out=_coerce_bool(
            row.get("cta_url_link_tracking_opted_out")
        ),
        library_template_name=coerce_string(row.get("library_template_name")),
        message_send_ttl_seconds=_coerce_int(row.get("message_send_ttl_seconds")),
        metadata=metadata,
        raw=row,
    )


def _parse_template_component_definition(payload: object) -> WhatsAppTemplateComponentDefinition:
    row = to_object(payload)
    known_keys = {"type", "format", "text", "buttons", "example"}
    return WhatsAppTemplateComponentDefinition(
        type=coerce_string(row.get("type")) or "",
        format=coerce_string(row.get("format")),
        text=coerce_string(row.get("text")),
        buttons=tuple(
            _parse_template_button_definition(item) for item in _normalize_rows(row.get("buttons"))
        ),
        example=to_object(row.get("example")),
        provider_options={key: value for key, value in row.items() if key not in known_keys},
    )


def _parse_template_button_definition(payload: object) -> WhatsAppTemplateButtonDefinition:
    row = to_object(payload)
    known_keys = {
        "type",
        "text",
        "phone_number",
        "url",
        "example",
        "flow_id",
        "flow_name",
        "flow_json",
        "flow_action",
        "navigate_screen",
        "otp_type",
        "zero_tap_terms_accepted",
        "supported_apps",
    }
    supported_apps = tuple(to_object(item) for item in _normalize_rows(row.get("supported_apps")))
    return WhatsAppTemplateButtonDefinition(
        type=coerce_string(row.get("type")) or "",
        text=coerce_string(row.get("text")),
        phone_number=coerce_string(row.get("phone_number")),
        url=coerce_string(row.get("url")),
        example=tuple(_normalize_text_sequence(row.get("example"), "buttons[].example[]")),
        flow_id=coerce_string(row.get("flow_id")),
        flow_name=coerce_string(row.get("flow_name")),
        flow_json=coerce_string(row.get("flow_json")),
        flow_action=coerce_string(row.get("flow_action")),
        navigate_screen=coerce_string(row.get("navigate_screen")),
        otp_type=coerce_string(row.get("otp_type")),
        zero_tap_terms_accepted=_coerce_bool(row.get("zero_tap_terms_accepted")),
        supported_apps=supported_apps,
        provider_options={key: value for key, value in row.items() if key not in known_keys},
    )


def _build_template_mutation_result(
    provider_name: str,
    response: Mapping[str, object],
    *,
    fallback_template_id: str | None = None,
) -> WhatsAppTemplateMutationResult:
    template_id = coerce_string(response.get("id")) or fallback_template_id
    success = _coerce_bool(response.get("success"))
    return WhatsAppTemplateMutationResult(
        provider=provider_name,
        success=success if success is not None else template_id is not None,
        template_id=template_id,
        name=coerce_string(response.get("name")),
        category=coerce_string(response.get("category")),
        status=coerce_string(response.get("status")),
        raw=response,
    )


def _build_template_delete_result(
    provider_name: str,
    request: WhatsAppTemplateDeleteRequest,
    response: Mapping[str, object],
) -> WhatsAppTemplateDeleteResult:
    return WhatsAppTemplateDeleteResult(
        provider=provider_name,
        deleted=bool(response.get("success")),
        name=coerce_string(request.name),
        template_id=coerce_string(request.template_id),
        template_ids=tuple(_normalize_text_sequence(request.template_ids, "template_ids[]")),
        raw=response,
    )


def _build_text_payload(request: WhatsAppTextRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {"body": _require_text(request.text, "text")}
    if request.preview_url is not None:
        payload["preview_url"] = request.preview_url
    return _build_message_payload(
        recipient=request.recipient,
        message_type="text",
        message_body=payload,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_template_payload(request: WhatsAppTemplateRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": _require_text(request.template_name, "template_name"),
        "language": {"code": _require_text(request.language_code, "language_code")},
    }
    if request.components:
        payload["components"] = [
            _build_template_component(component) for component in request.components
        ]
    return _build_message_payload(
        recipient=request.recipient,
        message_type="template",
        message_body=payload,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_media_payload(request: WhatsAppMediaRequest) -> dict[str, Any]:
    media_payload = _build_media_object(
        media_id=request.media_id,
        link=request.link,
        field_name="media",
    )
    if request.caption is not None and request.media_type in {"image", "video", "document"}:
        media_payload["caption"] = request.caption
    if request.filename is not None and request.media_type == "document":
        media_payload["filename"] = request.filename
    return _build_message_payload(
        recipient=request.recipient,
        message_type=request.media_type,
        message_body=media_payload,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_location_payload(request: WhatsAppLocationRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="location",
        message_body=_compact_mapping(
            {
                "latitude": request.latitude,
                "longitude": request.longitude,
                "name": coerce_string(request.name),
                "address": coerce_string(request.address),
            }
        ),
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_contacts_payload(request: WhatsAppContactsRequest) -> dict[str, Any]:
    if not request.contacts:
        raise ValueError("contacts must not be empty.")
    return _build_message_payload(
        recipient=request.recipient,
        message_type="contacts",
        message_body=[_build_contact(contact) for contact in request.contacts],
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_reaction_payload(request: WhatsAppReactionRequest) -> dict[str, Any]:
    return _build_message_payload(
        recipient=request.recipient,
        message_type="reaction",
        message_body={
            "message_id": _require_text(request.message_id, "message_id"),
            "emoji": _require_text(request.emoji, "emoji"),
        },
        reply_to_message_id=None,
        provider_options=request.provider_options,
    )


def _build_interactive_payload(request: WhatsAppInteractiveRequest) -> dict[str, Any]:
    interactive: dict[str, Any] = {
        "type": request.interactive_type,
        "body": {"text": _require_text(request.body_text, "body_text")},
    }
    if request.header is not None:
        interactive["header"] = _build_interactive_header(request.header)
    if request.footer_text is not None:
        interactive["footer"] = {"text": request.footer_text}

    if request.interactive_type == "button":
        if not request.buttons:
            raise ValueError("buttons must not be empty for button interactive messages.")
        interactive["action"] = {
            "buttons": [_build_interactive_button(button) for button in request.buttons]
        }
    elif request.interactive_type == "list":
        sections = [_build_interactive_section(section) for section in request.sections]
        if not sections:
            raise ValueError("sections must not be empty for list interactive messages.")
        interactive["action"] = {
            "button": _require_text(request.button_text, "button_text"),
            "sections": sections,
        }

    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=interactive,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_catalog_message_payload(request: WhatsAppCatalogMessageRequest) -> dict[str, Any]:
    interactive = _build_catalog_interactive_payload(request)
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=interactive,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_product_message_payload(request: WhatsAppProductMessageRequest) -> dict[str, Any]:
    interactive = _build_product_interactive_payload(request)
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=interactive,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_product_list_payload(request: WhatsAppProductListRequest) -> dict[str, Any]:
    interactive = _build_product_list_interactive_payload(request)
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=interactive,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_flow_message_payload(request: WhatsAppFlowMessageRequest) -> dict[str, Any]:
    interactive = _build_flow_interactive_payload(request)
    return _build_message_payload(
        recipient=request.recipient,
        message_type="interactive",
        message_body=interactive,
        reply_to_message_id=request.reply_to_message_id,
        provider_options=request.provider_options,
    )


def _build_message_payload(
    *,
    recipient: str,
    message_type: str,
    message_body: object,
    reply_to_message_id: str | None,
    provider_options: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(provider_options or {})
    payload.update(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": _require_text(recipient, "recipient"),
            "type": message_type,
            message_type: message_body,
        }
    )
    if reply_to_message_id is not None:
        payload["context"] = {"message_id": reply_to_message_id}
    return payload


def _build_template_component(component: WhatsAppTemplateComponent) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": component.type}
    if component.sub_type is not None:
        payload["sub_type"] = component.sub_type
    if component.index is not None:
        payload["index"] = component.index
    if component.parameters:
        payload["parameters"] = [
            _build_template_parameter(parameter) for parameter in component.parameters
        ]
    return payload


def _build_template_parameter(parameter: WhatsAppTemplateParameter) -> dict[str, Any]:
    payload = dict(parameter.provider_options or {})
    payload["type"] = parameter.type

    if parameter.value is not None:
        if parameter.type == "text":
            payload.setdefault("text", parameter.value)
        elif parameter.type == "payload":
            payload.setdefault("payload", parameter.value)
        elif parameter.type in {"image", "video", "document"}:
            nested = to_object(payload.get(parameter.type))
            if not nested:
                payload[parameter.type] = {"id": parameter.value}
        elif parameter.type not in payload:
            payload["text"] = parameter.value

    return payload


def _build_media_object(
    *,
    media_id: str | None,
    link: str | None,
    field_name: str,
) -> dict[str, str]:
    media_id = coerce_string(media_id)
    link = coerce_string(link)
    if media_id and link:
        raise ValueError(f"{field_name} accepts either media_id or link, not both.")
    if media_id is None and link is None:
        raise ValueError(f"{field_name} requires either media_id or link.")
    return {"id": media_id} if media_id is not None else {"link": link or ""}


def _build_contact(contact: WhatsAppContact) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": _compact_mapping(
            {
                "formatted_name": _require_text(
                    contact.name.formatted_name,
                    "contacts[].name.formatted_name",
                ),
                "first_name": coerce_string(contact.name.first_name),
                "last_name": coerce_string(contact.name.last_name),
                "middle_name": coerce_string(contact.name.middle_name),
                "suffix": coerce_string(contact.name.suffix),
                "prefix": coerce_string(contact.name.prefix),
            }
        )
    }
    if contact.phones:
        payload["phones"] = [_build_contact_phone(phone) for phone in contact.phones]
    if contact.emails:
        payload["emails"] = [_build_contact_email(email) for email in contact.emails]
    if contact.urls:
        payload["urls"] = [_build_contact_url(url) for url in contact.urls]
    if contact.addresses:
        payload["addresses"] = [
            _build_contact_address(address) for address in contact.addresses
        ]
    if contact.org is not None:
        payload["org"] = _build_contact_org(contact.org)
    if contact.birthday is not None:
        payload["birthday"] = contact.birthday
    return payload


def _build_contact_phone(phone: WhatsAppContactPhone) -> dict[str, str]:
    return _compact_mapping(
        {
            "phone": _require_text(phone.phone, "contacts[].phones[].phone"),
            "type": coerce_string(phone.type),
            "wa_id": coerce_string(phone.wa_id),
        }
    )


def _build_contact_email(email: WhatsAppContactEmail) -> dict[str, str]:
    return _compact_mapping(
        {
            "email": _require_text(email.email, "contacts[].emails[].email"),
            "type": coerce_string(email.type),
        }
    )


def _build_contact_url(url: WhatsAppContactUrl) -> dict[str, str]:
    return _compact_mapping(
        {
            "url": _require_text(url.url, "contacts[].urls[].url"),
            "type": coerce_string(url.type),
        }
    )


def _build_contact_address(address: WhatsAppContactAddress) -> dict[str, str]:
    return _compact_mapping(
        {
            "street": coerce_string(address.street),
            "city": coerce_string(address.city),
            "state": coerce_string(address.state),
            "zip": coerce_string(address.zip),
            "country": coerce_string(address.country),
            "country_code": coerce_string(address.country_code),
            "type": coerce_string(address.type),
        }
    )


def _build_contact_org(org: WhatsAppContactOrg) -> dict[str, str]:
    return _compact_mapping(
        {
            "company": coerce_string(org.company),
            "department": coerce_string(org.department),
            "title": coerce_string(org.title),
        }
    )


def _build_interactive_header(header: WhatsAppInteractiveHeader) -> dict[str, Any]:
    payload = dict(header.provider_options or {})
    payload["type"] = header.type
    if header.type == "text":
        payload.setdefault("text", _require_text(header.text, "header.text"))
        return payload

    media_payload = _build_media_object(
        media_id=header.media_id,
        link=header.link,
        field_name="header",
    )
    if header.filename is not None and header.type == "document":
        media_payload["filename"] = header.filename
    payload.setdefault(header.type, media_payload)
    return payload


def _build_interactive_button(button: WhatsAppInteractiveButton) -> dict[str, Any]:
    return {
        "type": "reply",
        "reply": {
            "id": _require_text(button.identifier, "buttons[].identifier"),
            "title": _require_text(button.title, "buttons[].title"),
        },
    }


def _build_interactive_section(section: WhatsAppInteractiveSection) -> dict[str, Any]:
    if not section.rows:
        raise ValueError("sections[].rows must not be empty.")
    payload: dict[str, Any] = {
        "rows": [_build_interactive_row(row) for row in section.rows],
    }
    if section.title is not None:
        payload["title"] = section.title
    return payload


def _build_interactive_row(row: WhatsAppInteractiveRow) -> dict[str, Any]:
    return _compact_mapping(
        {
            "id": _require_text(row.identifier, "sections[].rows[].identifier"),
            "title": _require_text(row.title, "sections[].rows[].title"),
            "description": coerce_string(row.description),
        }
    )


def _build_catalog_interactive_payload(request: WhatsAppCatalogMessageRequest) -> dict[str, Any]:
    interactive = _build_common_interactive_payload(
        interactive_type="catalog_message",
        body_text=request.body_text,
        header=request.header,
        footer_text=request.footer_text,
    )
    action: dict[str, Any] = {"name": "catalog_message"}
    if request.thumbnail_product_retailer_id is not None:
        action["parameters"] = {
            "thumbnail_product_retailer_id": _require_text(
                request.thumbnail_product_retailer_id,
                "thumbnail_product_retailer_id",
            )
        }
    interactive["action"] = action
    return interactive


def _build_product_interactive_payload(request: WhatsAppProductMessageRequest) -> dict[str, Any]:
    interactive = _build_common_interactive_payload(
        interactive_type="product",
        body_text=request.body_text,
        header=None,
        footer_text=request.footer_text,
    )
    interactive["action"] = {
        "catalog_id": _require_text(request.catalog_id, "catalog_id"),
        "product_retailer_id": _require_text(
            request.product_retailer_id,
            "product_retailer_id",
        ),
    }
    return interactive


def _build_product_list_interactive_payload(request: WhatsAppProductListRequest) -> dict[str, Any]:
    sections = [_build_product_section(section) for section in request.sections]
    if not sections:
        raise ValueError("sections must not be empty for product_list interactive messages.")
    if request.header is None:
        raise ValueError("header is required for product_list interactive messages.")
    interactive = _build_common_interactive_payload(
        interactive_type="product_list",
        body_text=request.body_text,
        header=request.header,
        footer_text=request.footer_text,
    )
    interactive["action"] = {
        "catalog_id": _require_text(request.catalog_id, "catalog_id"),
        "sections": sections,
    }
    return interactive


def _build_flow_interactive_payload(request: WhatsAppFlowMessageRequest) -> dict[str, Any]:
    interactive = _build_common_interactive_payload(
        interactive_type="flow",
        body_text=request.body_text,
        header=request.header,
        footer_text=request.footer_text,
    )
    parameters = _compact_mapping(
        {
            "flow_message_version": _require_text(
                request.flow_message_version,
                "flow_message_version",
            ),
            "flow_token": coerce_string(request.flow_token),
            "flow_id": coerce_string(request.flow_id),
            "flow_name": coerce_string(request.flow_name),
            "flow_cta": _require_text(request.flow_cta, "flow_cta"),
            "flow_action": _require_text(request.flow_action, "flow_action"),
        }
    )
    if ("flow_id" in parameters) == ("flow_name" in parameters):
        raise ValueError("flow messages require exactly one of flow_id or flow_name.")
    if request.flow_action_payload:
        parameters["flow_action_payload"] = dict(request.flow_action_payload)
    interactive["action"] = {
        "name": "flow",
        "parameters": parameters,
    }
    return interactive


def _build_common_interactive_payload(
    *,
    interactive_type: str,
    body_text: str | None,
    header: WhatsAppInteractiveHeader | None,
    footer_text: str | None,
) -> dict[str, Any]:
    interactive: dict[str, Any] = {"type": interactive_type}
    if body_text is not None:
        interactive["body"] = {"text": _require_text(body_text, "body_text")}
    if header is not None:
        interactive["header"] = _build_interactive_header(header)
    if footer_text is not None:
        interactive["footer"] = {"text": footer_text}
    return interactive


def _build_product_section(section: WhatsAppProductSection) -> dict[str, Any]:
    if not section.product_items:
        raise ValueError("sections[].product_items must not be empty.")
    return {
        "title": _require_text(section.title, "sections[].title"),
        "product_items": [_build_product_item(item) for item in section.product_items],
    }


def _build_product_item(item: WhatsAppProductItem) -> dict[str, Any]:
    return {
        "product_retailer_id": _require_text(
            item.product_retailer_id,
            "sections[].product_items[].product_retailer_id",
        )
    }


def _build_media_upload_form(request: WhatsAppMediaUploadRequest) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key, value in request.provider_options.items():
        payload[key] = _require_text(coerce_string(value), f"provider_options[{key}]")
    payload["messaging_product"] = "whatsapp"
    payload["type"] = _require_text(request.mime_type, "mime_type")
    return payload


def _build_media_upload_files(
    request: WhatsAppMediaUploadRequest,
) -> dict[str, tuple[str, bytes, str]]:
    content = bytes(request.content)
    if not content:
        raise ValueError("content must not be empty.")
    return {
        "file": (
            _require_text(request.filename, "filename"),
            content,
            _require_text(request.mime_type, "mime_type"),
        )
    }


def _iterate_value_objects(payload: Mapping[str, object]) -> tuple[dict[str, Any], ...]:
    root = to_object(payload)
    entries = root.get("entry")
    if not isinstance(entries, list):
        return ()

    values: list[dict[str, Any]] = []
    for entry in entries:
        changes = to_object(entry).get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            values.append(to_object(to_object(change).get("value")))
    return tuple(values)


def _build_profile_lookup(value: object) -> dict[str, str | None]:
    contacts = value if isinstance(value, list) else []
    profiles: dict[str, str | None] = {}
    for row in contacts:
        payload = to_object(row)
        wa_id = coerce_string(payload.get("wa_id"))
        if wa_id is not None:
            profiles[wa_id] = coerce_string(to_object(payload.get("profile")).get("name"))
    return profiles


def _build_inbound_message(
    *,
    provider_name: str,
    payload: object,
    profiles: Mapping[str, str | None],
    webhook_metadata: Mapping[str, object],
) -> WhatsAppInboundMessage | None:
    message = to_object(payload)
    sender_id = coerce_string(message.get("from"))
    message_id = coerce_string(message.get("id"))
    if sender_id is None or message_id is None:
        return None

    raw_type = coerce_string(message.get("type")) or "unsupported"
    context = to_object(message.get("context"))
    referral = to_object(message.get("referral"))
    metadata = _compact_mapping(
        {
            "display_phone_number": coerce_string(webhook_metadata.get("display_phone_number")),
            "phone_number_id": coerce_string(webhook_metadata.get("phone_number_id")),
            "referral": referral or None,
            "provider_message_type": raw_type if raw_type == "unsupported" else None,
        }
    )

    text = None
    media = None
    location = None
    contacts: tuple[WhatsAppContact, ...] = ()
    reply = None
    reaction = None
    message_type = raw_type

    if raw_type == "text":
        text = coerce_string(to_object(message.get("text")).get("body"))
    elif raw_type in _MEDIA_TYPES:
        media = _build_inbound_media(raw_type, message.get(raw_type))
    elif raw_type == "location":
        location = _build_inbound_location(message.get("location"))
    elif raw_type == "contacts":
        contacts = _parse_contact_list(message.get("contacts"))
    elif raw_type == "button":
        reply = _build_button_reply(message.get("button"))
    elif raw_type == "interactive":
        reply = _build_interactive_reply(message.get("interactive"))
    elif raw_type == "reaction":
        reaction = _build_inbound_reaction(message.get("reaction"))
    else:
        message_type = "unsupported"
        metadata = {**metadata, "provider_message_type": raw_type}

    return WhatsAppInboundMessage(
        provider=provider_name,
        sender_id=sender_id,
        message_id=message_id,
        message_type=message_type,  # type: ignore[arg-type]
        timestamp=coerce_string(message.get("timestamp")),
        profile_name=profiles.get(sender_id),
        context_message_id=coerce_string(context.get("message_id")),
        forwarded=_coerce_bool(context.get("forwarded")),
        frequently_forwarded=_coerce_bool(context.get("frequently_forwarded")),
        text=text,
        media=media,
        location=location,
        contacts=contacts,
        reply=reply,
        reaction=reaction,
        metadata=metadata,
        raw=message,
    )


def _build_inbound_media(message_type: str, payload: object) -> WhatsAppInboundMedia | None:
    data = to_object(payload)
    if not data:
        return None
    return WhatsAppInboundMedia(
        media_type=message_type,  # type: ignore[arg-type]
        media_id=coerce_string(data.get("id")),
        mime_type=coerce_string(data.get("mime_type")),
        sha256=coerce_string(data.get("sha256")),
        caption=coerce_string(data.get("caption")),
        filename=coerce_string(data.get("filename")),
        raw=data,
    )


def _build_inbound_location(payload: object) -> WhatsAppInboundLocation | None:
    data = to_object(payload)
    if not data:
        return None
    return WhatsAppInboundLocation(
        latitude=_coerce_float(data.get("latitude")),
        longitude=_coerce_float(data.get("longitude")),
        name=coerce_string(data.get("name")),
        address=coerce_string(data.get("address")),
        url=coerce_string(data.get("url")),
        raw=data,
    )


def _build_button_reply(payload: object) -> WhatsAppInboundReply | None:
    data = to_object(payload)
    if not data:
        return None
    return WhatsAppInboundReply(
        reply_type="button",
        payload=coerce_string(data.get("payload")),
        title=coerce_string(data.get("text")),
        raw=data,
    )


def _build_interactive_reply(payload: object) -> WhatsAppInboundReply | None:
    data = to_object(payload)
    reply_type = coerce_string(data.get("type"))
    if reply_type == "button_reply":
        reply = to_object(data.get("button_reply"))
        return WhatsAppInboundReply(
            reply_type="button_reply",
            identifier=coerce_string(reply.get("id")),
            title=coerce_string(reply.get("title")),
            raw=data,
        )
    if reply_type == "list_reply":
        reply = to_object(data.get("list_reply"))
        return WhatsAppInboundReply(
            reply_type="list_reply",
            identifier=coerce_string(reply.get("id")),
            title=coerce_string(reply.get("title")),
            description=coerce_string(reply.get("description")),
            raw=data,
        )
    return None


def _build_inbound_reaction(payload: object) -> WhatsAppInboundReaction | None:
    data = to_object(payload)
    if not data:
        return None
    return WhatsAppInboundReaction(
        emoji=coerce_string(data.get("emoji")),
        related_message_id=coerce_string(data.get("message_id")),
        raw=data,
    )


def _parse_contact_list(value: object) -> tuple[WhatsAppContact, ...]:
    rows = value if isinstance(value, list) else []
    contacts = [_parse_contact(row) for row in rows]
    return tuple(contact for contact in contacts if contact is not None)


def _parse_contact(value: object) -> WhatsAppContact | None:
    payload = to_object(value)
    name_payload = to_object(payload.get("name"))
    formatted_name = coerce_string(name_payload.get("formatted_name"))
    if formatted_name is None:
        return None

    return WhatsAppContact(
        name=WhatsAppContactName(
            formatted_name=formatted_name,
            first_name=coerce_string(name_payload.get("first_name")),
            last_name=coerce_string(name_payload.get("last_name")),
            middle_name=coerce_string(name_payload.get("middle_name")),
            suffix=coerce_string(name_payload.get("suffix")),
            prefix=coerce_string(name_payload.get("prefix")),
        ),
        phones=tuple(_parse_contact_phone(row) for row in _normalize_rows(payload.get("phones"))),
        emails=tuple(_parse_contact_email(row) for row in _normalize_rows(payload.get("emails"))),
        urls=tuple(_parse_contact_url(row) for row in _normalize_rows(payload.get("urls"))),
        addresses=tuple(
            _parse_contact_address(row) for row in _normalize_rows(payload.get("addresses"))
        ),
        org=_parse_contact_org(payload.get("org")),
        birthday=coerce_string(payload.get("birthday")),
    )


def _parse_contact_phone(value: object) -> WhatsAppContactPhone:
    payload = to_object(value)
    return WhatsAppContactPhone(
        phone=coerce_string(payload.get("phone")) or "",
        type=coerce_string(payload.get("type")),
        wa_id=coerce_string(payload.get("wa_id")),
    )


def _parse_contact_email(value: object) -> WhatsAppContactEmail:
    payload = to_object(value)
    return WhatsAppContactEmail(
        email=coerce_string(payload.get("email")) or "",
        type=coerce_string(payload.get("type")),
    )


def _parse_contact_url(value: object) -> WhatsAppContactUrl:
    payload = to_object(value)
    return WhatsAppContactUrl(
        url=coerce_string(payload.get("url")) or "",
        type=coerce_string(payload.get("type")),
    )


def _parse_contact_address(value: object) -> WhatsAppContactAddress:
    payload = to_object(value)
    return WhatsAppContactAddress(
        street=coerce_string(payload.get("street")),
        city=coerce_string(payload.get("city")),
        state=coerce_string(payload.get("state")),
        zip=coerce_string(payload.get("zip")),
        country=coerce_string(payload.get("country")),
        country_code=coerce_string(payload.get("country_code")),
        type=coerce_string(payload.get("type")),
    )


def _parse_contact_org(value: object) -> WhatsAppContactOrg | None:
    payload = to_object(value)
    if not payload:
        return None
    return WhatsAppContactOrg(
        company=coerce_string(payload.get("company")),
        department=coerce_string(payload.get("department")),
        title=coerce_string(payload.get("title")),
    )


def _normalize_rows(value: object) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    return [to_object(row) for row in rows]


def _first_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, list):
        return to_object(value[0]) if value else {}
    return to_object(value)


def _set_query_value(
    query: dict[str, str],
    key: str,
    value: object,
    *,
    uppercase: bool = False,
) -> None:
    if value is None:
        return
    if isinstance(value, (str, int)):
        text = _require_text(coerce_string(value), key)
        query[key] = text.upper() if uppercase else text
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        items = _normalize_text_sequence(value, f"{key}[]")
        if not items:
            return
        normalized = [item.upper() for item in items] if uppercase else list(items)
        query[key] = ",".join(normalized)
        return
    text = _require_text(coerce_string(value), key)
    query[key] = text.upper() if uppercase else text


def _normalize_text_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_require_text(value, field_name),)
    if not isinstance(value, Sequence):
        return ()
    items = [
        _require_text(coerce_string(item), field_name)
        for item in value
        if not isinstance(item, (bytes, bytearray, memoryview))
    ]
    return tuple(items)


def _normalize_template_enum(value: str, field_name: str) -> str:
    return _require_text(value, field_name).upper()


def _map_whatsapp_state(status: str | None) -> str:
    normalized = (status or "").lower()
    if normalized in {"accepted", "sent"}:
        return "submitted"
    if normalized == "delivered":
        return "delivered"
    if normalized == "read":
        return "read"
    if normalized == "failed":
        return "failed"
    return "unknown"


def _compact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (float, int)):
        return float(value)
    text = coerce_string(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = coerce_string(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _require_text(value: str | None, field_name: str) -> str:
    text = coerce_string(value)
    if text is None:
        raise ConfigurationError(f"{field_name} is required.")
    return text
