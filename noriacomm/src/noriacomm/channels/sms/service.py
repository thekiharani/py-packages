from __future__ import annotations

from collections.abc import Mapping

from ...events import DeliveryEvent
from ...exceptions import ConfigurationError
from ...types import RequestOptions
from .gateways.base import (
    AsyncSmsGateway,
    AsyncSmsManagementGateway,
    SmsGateway,
    SmsManagementGateway,
)
from .models import (
    SmsBalance,
    SmsGroup,
    SmsGroupUpsertRequest,
    SmsManagementResult,
    SmsSendRequest,
    SmsSendResult,
    SmsTemplate,
    SmsTemplateUpsertRequest,
)


class SmsService:
    def __init__(self, gateway: SmsGateway | None) -> None:
        self.gateway = gateway

    @property
    def configured(self) -> bool:
        return self.gateway is not None

    @property
    def provider(self) -> str | None:
        if self.gateway is None:
            return None
        return self.gateway.provider_name

    def send(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult:
        return _require_gateway(self.gateway).send(request, options=options)

    def get_balance(self, *, options: RequestOptions | None = None) -> SmsBalance | None:
        return _require_gateway(self.gateway).get_balance(options=options)

    def list_groups(self, *, options: RequestOptions | None = None) -> tuple[SmsGroup, ...]:
        return _require_management_gateway(self.gateway).list_groups(options=options)

    def create_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return _require_management_gateway(self.gateway).create_group(request, options=options)

    def update_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return _require_management_gateway(self.gateway).update_group(
            group_id,
            request,
            options=options,
        )

    def delete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return _require_management_gateway(self.gateway).delete_group(group_id, options=options)

    def list_templates(self, *, options: RequestOptions | None = None) -> tuple[SmsTemplate, ...]:
        return _require_management_gateway(self.gateway).list_templates(options=options)

    def create_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return _require_management_gateway(self.gateway).create_template(request, options=options)

    def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return _require_management_gateway(self.gateway).update_template(
            template_id,
            request,
            options=options,
        )

    def delete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return _require_management_gateway(self.gateway).delete_template(
            template_id,
            options=options,
        )

    def parse_delivery_report(self, payload: Mapping[str, object]) -> DeliveryEvent | None:
        return _require_gateway(self.gateway).parse_delivery_report(payload)

    def close(self) -> None:
        if self.gateway is not None:
            self.gateway.close()


class AsyncSmsService:
    def __init__(self, gateway: AsyncSmsGateway | None) -> None:
        self.gateway = gateway

    @property
    def configured(self) -> bool:
        return self.gateway is not None

    @property
    def provider(self) -> str | None:
        if self.gateway is None:
            return None
        return self.gateway.provider_name

    async def send(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult:
        return await _require_async_gateway(self.gateway).asend(request, options=options)

    async def get_balance(self, *, options: RequestOptions | None = None) -> SmsBalance | None:
        return await _require_async_gateway(self.gateway).aget_balance(options=options)

    async def list_groups(self, *, options: RequestOptions | None = None) -> tuple[SmsGroup, ...]:
        return await _require_async_management_gateway(self.gateway).alist_groups(options=options)

    async def create_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return await _require_async_management_gateway(self.gateway).acreate_group(
            request,
            options=options,
        )

    async def update_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return await _require_async_management_gateway(self.gateway).aupdate_group(
            group_id,
            request,
            options=options,
        )

    async def delete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return await _require_async_management_gateway(self.gateway).adelete_group(
            group_id,
            options=options,
        )

    async def list_templates(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsTemplate, ...]:
        return await _require_async_management_gateway(self.gateway).alist_templates(
            options=options,
        )

    async def create_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return await _require_async_management_gateway(self.gateway).acreate_template(
            request,
            options=options,
        )

    async def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return await _require_async_management_gateway(self.gateway).aupdate_template(
            template_id,
            request,
            options=options,
        )

    async def delete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult:
        return await _require_async_management_gateway(self.gateway).adelete_template(
            template_id,
            options=options,
        )

    def parse_delivery_report(self, payload: Mapping[str, object]) -> DeliveryEvent | None:
        return _require_async_gateway(self.gateway).parse_delivery_report(payload)

    async def aclose(self) -> None:
        if self.gateway is not None:
            await self.gateway.aclose()


def _require_gateway(gateway: SmsGateway | None) -> SmsGateway:
    if gateway is None:
        raise ConfigurationError("SMS gateway is not configured on this client.")
    return gateway


def _require_async_gateway(gateway: AsyncSmsGateway | None) -> AsyncSmsGateway:
    if gateway is None:
        raise ConfigurationError("SMS gateway is not configured on this client.")
    return gateway


def _require_management_gateway(gateway: SmsGateway | None) -> SmsManagementGateway:
    if gateway is None or not isinstance(gateway, SmsManagementGateway):
        raise ConfigurationError(
            "Configured SMS gateway does not support group/template management."
        )
    return gateway


def _require_async_management_gateway(
    gateway: AsyncSmsGateway | None,
) -> AsyncSmsManagementGateway:
    if gateway is None or not isinstance(gateway, AsyncSmsManagementGateway):
        raise ConfigurationError(
            "Configured SMS gateway does not support group/template management."
        )
    return gateway
