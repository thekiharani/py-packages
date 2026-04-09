from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from ....events import DeliveryEvent
from ....types import RequestOptions
from ..models import (
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


@runtime_checkable
class WhatsAppGateway(Protocol):
    provider_name: str

    def send_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def send_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    def upload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult: ...

    def get_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo: ...

    def delete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult: ...

    def parse_events(self, payload: Mapping[str, object]) -> tuple[DeliveryEvent, ...]: ...

    def parse_event(self, payload: Mapping[str, object]) -> DeliveryEvent | None: ...

    def parse_inbound_messages(
        self,
        payload: Mapping[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]: ...

    def parse_inbound_message(
        self,
        payload: Mapping[str, object],
    ) -> WhatsAppInboundMessage | None: ...

    def close(self) -> None: ...


@runtime_checkable
class AsyncWhatsAppGateway(Protocol):
    provider_name: str

    async def asend_text(
        self,
        request: WhatsAppTextRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_template(
        self,
        request: WhatsAppTemplateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_media(
        self,
        request: WhatsAppMediaRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_location(
        self,
        request: WhatsAppLocationRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_contacts(
        self,
        request: WhatsAppContactsRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_reaction(
        self,
        request: WhatsAppReactionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_interactive(
        self,
        request: WhatsAppInteractiveRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_catalog(
        self,
        request: WhatsAppCatalogMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_product(
        self,
        request: WhatsAppProductMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_product_list(
        self,
        request: WhatsAppProductListRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def asend_flow(
        self,
        request: WhatsAppFlowMessageRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppSendResult: ...

    async def aupload_media(
        self,
        request: WhatsAppMediaUploadRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaUploadResult: ...

    async def aget_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaInfo: ...

    async def adelete_media(
        self,
        media_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppMediaDeleteResult: ...

    def parse_events(self, payload: Mapping[str, object]) -> tuple[DeliveryEvent, ...]: ...

    def parse_event(self, payload: Mapping[str, object]) -> DeliveryEvent | None: ...

    def parse_inbound_messages(
        self,
        payload: Mapping[str, object],
    ) -> tuple[WhatsAppInboundMessage, ...]: ...

    def parse_inbound_message(
        self,
        payload: Mapping[str, object],
    ) -> WhatsAppInboundMessage | None: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class WhatsAppTemplateManagementGateway(Protocol):
    def list_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult: ...

    def get_template(
        self,
        template_id: str,
        *,
        fields: Sequence[str] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate: ...

    def create_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult: ...

    def update_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult: ...

    def delete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult: ...


@runtime_checkable
class AsyncWhatsAppTemplateManagementGateway(Protocol):
    async def alist_templates(
        self,
        request: WhatsAppTemplateListRequest | None = None,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateListResult: ...

    async def aget_template(
        self,
        template_id: str,
        *,
        fields: Sequence[str] = (),
        options: RequestOptions | None = None,
    ) -> WhatsAppManagedTemplate: ...

    async def acreate_template(
        self,
        request: WhatsAppTemplateCreateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult: ...

    async def aupdate_template(
        self,
        template_id: str,
        request: WhatsAppTemplateUpdateRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateMutationResult: ...

    async def adelete_template(
        self,
        request: WhatsAppTemplateDeleteRequest,
        *,
        options: RequestOptions | None = None,
    ) -> WhatsAppTemplateDeleteResult: ...
