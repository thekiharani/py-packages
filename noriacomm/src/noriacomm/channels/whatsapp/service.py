from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...events import DeliveryEvent
from ...exceptions import ConfigurationError
from ...types import RequestOptions
from .gateways.base import (
    AsyncWhatsAppGateway,
    AsyncWhatsAppTemplateManagementGateway,
    WhatsAppGateway,
    WhatsAppTemplateManagementGateway,
)
from .models import (
    WhatsAppCatalogMessageRequest,
    WhatsAppContactsRequest,
    WhatsAppFlowMessageRequest,
    WhatsAppInboundMessage,
    WhatsAppInteractiveRequest,
    WhatsAppLocationRequest,
    WhatsAppManagedTemplate,
    WhatsAppMediaDeleteResult,
    WhatsAppMediaInfo,
    WhatsAppMediaRequest,
    WhatsAppMediaUploadRequest,
    WhatsAppMediaUploadResult,
    WhatsAppProductListRequest,
    WhatsAppProductMessageRequest,
    WhatsAppReactionRequest,
    WhatsAppSendResult,
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateDeleteRequest,
    WhatsAppTemplateDeleteResult,
    WhatsAppTemplateListRequest,
    WhatsAppTemplateListResult,
    WhatsAppTemplateMutationResult,
    WhatsAppTemplateRequest,
    WhatsAppTemplateUpdateRequest,
    WhatsAppTextRequest,
)


class WhatsAppService:
    def __init__(self, gateway: WhatsAppGateway | None) -> None:
        self.gateway = gateway

    @property
    def configured(self) -> bool:
        return self.gateway is not None

    @property
    def provider(self) -> str | None:
        if self.gateway is None:
            return None
        return self.gateway.provider_name

    def send_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_text(request, options=options)

    def send_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_template(request, options=options)

    def list_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        return _require_template_management_gateway(self.gateway).list_templates(
            request,
            options=options,
        )

    def get_template(
        self,
        template_id: str,
        *,
        fields: Sequence[str] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        return _require_template_management_gateway(self.gateway).get_template(
            template_id,
            fields=fields,
            options=options,
        )

    def create_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        return _require_template_management_gateway(self.gateway).create_template(
            request,
            options=options,
        )

    def update_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        return _require_template_management_gateway(self.gateway).update_template(
            template_id,
            request,
            options=options,
        )

    def delete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult:
        return _require_template_management_gateway(self.gateway).delete_template(
            request,
            options=options,
        )

    def send_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_media(request, options=options)

    def send_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_location(request, options=options)

    def send_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_contacts(request, options=options)

    def send_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_reaction(request, options=options)

    def send_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_interactive(request, options=options)

    def send_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_catalog(request, options=options)

    def send_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_product(request, options=options)

    def send_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_product_list(request, options=options)

    def send_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return _require_gateway(self.gateway).send_flow(request, options=options)

    def upload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult:
        return _require_gateway(self.gateway).upload_media(request, options=options)

    def get_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo:
        return _require_gateway(self.gateway).get_media(media_id, options=options)

    def delete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult:
        return _require_gateway(self.gateway).delete_media(media_id, options=options)

    def parse_events(self, payload: Mapping[str, object]) -> tuple[DeliveryEvent, ...]:
        return _require_gateway(self.gateway).parse_events(payload)

    def parse_event(self, payload: Mapping[str, object]) -> DeliveryEvent | None:
        events = self.parse_events(payload)
        return events[0] if events else None

    def parse_inbound_messages(
        self,
        payload: Mapping[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]:
        return _require_gateway(self.gateway).parse_inbound_messages(payload)

    def parse_inbound_message(self, payload: Mapping[str, object]) -> WhatsAppInboundMessage | None:
        messages = self.parse_inbound_messages(payload)
        return messages[0] if messages else None

    def close(self) -> None:
        if self.gateway is not None:
            self.gateway.close()


class AsyncWhatsAppService:
    def __init__(self, gateway: AsyncWhatsAppGateway | None) -> None:
        self.gateway = gateway

    @property
    def configured(self) -> bool:
        return self.gateway is not None

    @property
    def provider(self) -> str | None:
        if self.gateway is None:
            return None
        return self.gateway.provider_name

    async def send_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_text(request, options=options)

    async def send_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_template(request, options=options)

    async def list_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult:
        return await _require_async_template_management_gateway(self.gateway).alist_templates(
            request,
            options=options,
        )

    async def get_template(
        self,
        template_id: str,
        *,
        fields: Sequence[str] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate:
        return await _require_async_template_management_gateway(self.gateway).aget_template(
            template_id,
            fields=fields,
            options=options,
        )

    async def create_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        return await _require_async_template_management_gateway(self.gateway).acreate_template(
            request,
            options=options,
        )

    async def update_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult:
        return await _require_async_template_management_gateway(self.gateway).aupdate_template(
            template_id,
            request,
            options=options,
        )

    async def delete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult:
        return await _require_async_template_management_gateway(self.gateway).adelete_template(
            request,
            options=options,
        )

    async def send_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_media(request, options=options)

    async def send_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_location(request, options=options)

    async def send_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_contacts(request, options=options)

    async def send_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_reaction(request, options=options)

    async def send_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_interactive(
            request,
            options=options,
        )

    async def send_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_catalog(request, options=options)

    async def send_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_product(request, options=options)

    async def send_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_product_list(
            request,
            options=options,
        )

    async def send_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult:
        return await _require_async_gateway(self.gateway).asend_flow(request, options=options)

    async def upload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult:
        return await _require_async_gateway(self.gateway).aupload_media(request, options=options)

    async def get_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo:
        return await _require_async_gateway(self.gateway).aget_media(media_id, options=options)

    async def delete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult:
        return await _require_async_gateway(self.gateway).adelete_media(
            media_id,
            options=options,
        )

    def parse_events(self, payload: Mapping[str, object]) -> tuple[DeliveryEvent, ...]:
        return _require_async_gateway(self.gateway).parse_events(payload)

    def parse_event(self, payload: Mapping[str, object]) -> DeliveryEvent | None:
        events = self.parse_events(payload)
        return events[0] if events else None

    def parse_inbound_messages(
        self,
        payload: Mapping[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]:
        return _require_async_gateway(self.gateway).parse_inbound_messages(payload)

    def parse_inbound_message(self, payload: Mapping[str, object]) -> WhatsAppInboundMessage | None:
        messages = self.parse_inbound_messages(payload)
        return messages[0] if messages else None

    async def aclose(self) -> None:
        if self.gateway is not None:
            await self.gateway.aclose()


def _require_gateway(gateway: WhatsAppGateway | None) -> WhatsAppGateway:
    if gateway is None:
        raise ConfigurationError("WhatsApp gateway is not configured on this client.")
    return gateway


def _require_async_gateway(gateway: AsyncWhatsAppGateway | None) -> AsyncWhatsAppGateway:
    if gateway is None:
        raise ConfigurationError("WhatsApp gateway is not configured on this client.")
    return gateway


def _require_template_management_gateway(
    gateway: WhatsAppGateway | None,
) -> WhatsAppTemplateManagementGateway:
    if gateway is None or not isinstance(gateway, WhatsAppTemplateManagementGateway):
        raise ConfigurationError(
            "Configured WhatsApp gateway does not support template management."
        )
    return gateway


def _require_async_template_management_gateway(
    gateway: AsyncWhatsAppGateway | None,
) -> AsyncWhatsAppTemplateManagementGateway:
    if gateway is None or not isinstance(gateway, AsyncWhatsAppTemplateManagementGateway):
        raise ConfigurationError(
            "Configured WhatsApp gateway does not support template management."
        )
    return gateway
