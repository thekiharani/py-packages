from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from ....events import DeliveryEvent
from ....types import RequestOptions
from ..models import (
    SmsBalance,
    SmsGroup,
    SmsGroupUpsertRequest,
    SmsManagementResult,
    SmsSendRequest,
    SmsSendResult,
    SmsTemplate,
    SmsTemplateUpsertRequest,
)


@runtime_checkable
class SmsGateway(Protocol):
    provider_name: str

    def send(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult: ...

    def get_balance(self, *, options: RequestOptions | None = None) -> SmsBalance | None: ...

    def parse_delivery_report(self, payload: Mapping[str, object]) -> DeliveryEvent | None: ...

    def close(self) -> None: ...


@runtime_checkable
class AsyncSmsGateway(Protocol):
    provider_name: str

    async def asend(
        self,
        request: SmsSendRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsSendResult: ...

    async def aget_balance(self, *, options: RequestOptions | None = None) -> SmsBalance | None: ...

    def parse_delivery_report(self, payload: Mapping[str, object]) -> DeliveryEvent | None: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class SmsManagementGateway(Protocol):
    def list_groups(self, *, options: RequestOptions | None = None) -> tuple[SmsGroup, ...]: ...

    def create_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    def update_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    def delete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    def list_templates(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsTemplate, ...]: ...

    def create_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    def update_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    def delete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...


@runtime_checkable
class AsyncSmsManagementGateway(Protocol):
    async def alist_groups(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsGroup, ...]: ...

    async def acreate_group(
        self,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    async def aupdate_group(
        self,
        group_id: str,
        request: SmsGroupUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    async def adelete_group(
        self,
        group_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    async def alist_templates(
        self,
        *,
        options: RequestOptions | None = None,
    ) -> tuple[SmsTemplate, ...]: ...

    async def acreate_template(
        self,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    async def aupdate_template(
        self,
        template_id: str,
        request: SmsTemplateUpsertRequest,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...

    async def adelete_template(
        self,
        template_id: str,
        *,
        options: RequestOptions | None = None,
    ) -> SmsManagementResult: ...
